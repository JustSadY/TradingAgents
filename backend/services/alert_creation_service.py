"""Guarded creation and re-arming of user price alerts.

The alert repository intentionally stays a small persistence layer.  This
service owns the policy that needs a transaction-wide view of both a user's
settings and their alerts.  Every production creation path goes through the
functions below, so a row lock on ``AppSettings`` serializes the count/check/
insert sequence on PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.alert import PriceAlert
from backend.models.settings import AppSettings

_logger = logging.getLogger(__name__)

ALERT_SOURCE_MANUAL = "manual"
ALERT_SOURCE_ASSISTANT = "assistant"
ALERT_SOURCE_ANALYSIS = "analysis"
_ALERT_SOURCES = frozenset({ALERT_SOURCE_MANUAL, ALERT_SOURCE_ASSISTANT, ALERT_SOURCE_ANALYSIS})


class AlertGuardrailViolation(RuntimeError):
    """A user-configured alert limit rejected a new or re-armed alert."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _now() -> datetime:
    """Small seam for deterministic cooldown tests."""
    return datetime.now(UTC)


async def _lock_user_settings(db: AsyncSession, user_id: int) -> AppSettings:
    """Return the user's settings after acquiring the creation-policy lock.

    The unique settings-owner index means one row is enough to serialize all
    alert writers for a user.  ``get_or_create_settings`` handles the rare
    first-request race; the following ``FOR UPDATE`` is the actual lock used
    by the count-and-insert critical section.
    """
    statement = select(AppSettings).where(AppSettings.user_id == user_id).with_for_update()
    settings = (await db.execute(statement)).scalar_one_or_none()
    if settings is not None:
        return settings

    from backend.models.user import User
    from backend.services.settings_service import get_or_create_settings

    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("Cannot create an alert for a missing user")
    await get_or_create_settings(db, user)
    settings = (await db.execute(statement)).scalar_one()
    return settings


async def _active_alert_count(db: AsyncSession, user_id: int, *, exclude_alert_id: int | None = None) -> int:
    statement = select(func.count(PriceAlert.id)).where(
        PriceAlert.user_id == user_id,
        PriceAlert.enabled.is_(True),
        PriceAlert.triggered_at.is_(None),
    )
    if exclude_alert_id is not None:
        statement = statement.where(PriceAlert.id != exclude_alert_id)
    return int((await db.execute(statement)).scalar_one())


async def _enforce_active_cap(
    db: AsyncSession,
    settings: AppSettings,
    user_id: int,
    *,
    exclude_alert_id: int | None = None,
) -> None:
    max_active_alerts = int(getattr(settings, "max_active_alerts", 30) or 30)
    active_count = await _active_alert_count(db, user_id, exclude_alert_id=exclude_alert_id)
    if active_count >= max_active_alerts:
        raise AlertGuardrailViolation(
            "active_limit",
            f"Your active alert limit ({max_active_alerts}) has been reached. Disable or delete an alert first.",
        )


async def _enforce_ai_run_cap(
    db: AsyncSession,
    settings: AppSettings,
    user_id: int,
    run_id: str,
) -> None:
    max_per_run = int(getattr(settings, "max_ai_alerts_per_run", 3) or 0)
    if max_per_run == 0:
        raise AlertGuardrailViolation("ai_run_disabled", "AI-generated alerts are disabled in Alert Settings.")

    count = int(
        (
            await db.execute(
                select(func.count(PriceAlert.id)).where(
                    PriceAlert.user_id == user_id,
                    PriceAlert.creation_source == ALERT_SOURCE_ANALYSIS,
                    PriceAlert.creation_run_id == run_id,
                )
            )
        ).scalar_one()
    )
    if count >= max_per_run:
        raise AlertGuardrailViolation(
            "ai_run_limit",
            f"This analysis has already created the maximum of {max_per_run} AI alerts.",
        )


async def _enforce_ai_cooldown(
    db: AsyncSession,
    settings: AppSettings,
    user_id: int,
    *,
    ticker: str,
    condition: str,
    alert_type: str,
    run_id: str,
    now: datetime,
) -> None:
    cooldown_hours = int(getattr(settings, "ai_alert_cooldown_hours", 24) or 0)
    if cooldown_hours == 0:
        return

    cutoff = now - timedelta(hours=cooldown_hours)
    prior = (
        await db.execute(
            select(PriceAlert.id)
            .where(
                PriceAlert.user_id == user_id,
                PriceAlert.creation_source == ALERT_SOURCE_ANALYSIS,
                PriceAlert.ticker == ticker,
                PriceAlert.condition == condition,
                PriceAlert.alert_type == alert_type,
                # A run may intentionally surface several distinct levels;
                # its own cap governs that batch. Cooldown prevents the next
                # scan from repeating an equivalent alert soon afterwards.
                PriceAlert.creation_run_id != run_id,
                PriceAlert.created_at >= cutoff,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if prior is not None:
        raise AlertGuardrailViolation(
            "ai_cooldown",
            f"An equivalent AI alert was created within the last {cooldown_hours} hour(s).",
        )


async def _has_active_exact_alert(
    db: AsyncSession,
    user_id: int,
    *,
    ticker: str,
    condition: str,
    target_price: Decimal,
    alert_type: str,
) -> bool:
    result = await db.execute(
        select(PriceAlert.id)
        .where(
            PriceAlert.user_id == user_id,
            PriceAlert.ticker == ticker,
            PriceAlert.condition == condition,
            PriceAlert.target_price == target_price,
            PriceAlert.alert_type == alert_type,
            PriceAlert.enabled.is_(True),
            PriceAlert.triggered_at.is_(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def create_alert_with_guardrails(
    db: AsyncSession,
    *,
    user_id: int,
    ticker: str,
    condition: str,
    target_price: float,
    auto_analyze: bool,
    alert_type: str = "price",
    creation_source: str = ALERT_SOURCE_MANUAL,
    creation_run_id: str | None = None,
    skip_if_limited: bool = False,
) -> PriceAlert | None:
    """Create an alert after atomically applying the user's guardrails.

    Manual and assistant-created alerts obey ``max_active_alerts`` only.
    They remain intentionally flexible: a user can choose multiple levels for
    the same ticker.  Alerts inferred by an analysis additionally obey the
    per-run cap and equivalent-alert cooldown.  Automated callers pass
    ``skip_if_limited=True`` so a deliberate limit cannot roll back unrelated
    analysis persistence.
    """
    normalized_source = creation_source.strip().lower()
    if normalized_source not in _ALERT_SOURCES:
        raise ValueError(f"Unsupported alert creation source: {creation_source!r}")
    if normalized_source == ALERT_SOURCE_ANALYSIS and not creation_run_id:
        raise ValueError("AI-generated alerts require an analysis run ID")

    normalized_ticker = ticker.strip().upper()
    normalized_condition = condition.strip().lower()
    normalized_alert_type = alert_type.strip().lower()
    if not normalized_ticker:
        raise ValueError("Alert ticker is required")
    if normalized_condition not in {"above", "below"}:
        raise ValueError("Alert condition must be 'above' or 'below'")

    try:
        settings = await _lock_user_settings(db, user_id)
        await _enforce_active_cap(db, settings, user_id)

        if normalized_source == ALERT_SOURCE_ANALYSIS:
            assert creation_run_id is not None  # narrowed above; keeps mypy honest
            await _enforce_ai_run_cap(db, settings, user_id, creation_run_id)
            now = _now()
            target_decimal = Decimal(str(target_price))
            if await _has_active_exact_alert(
                db,
                user_id,
                ticker=normalized_ticker,
                condition=normalized_condition,
                target_price=target_decimal,
                alert_type=normalized_alert_type,
            ):
                raise AlertGuardrailViolation("duplicate", "An equivalent active AI alert already exists.")
            await _enforce_ai_cooldown(
                db,
                settings,
                user_id,
                ticker=normalized_ticker,
                condition=normalized_condition,
                alert_type=normalized_alert_type,
                run_id=creation_run_id,
                now=now,
            )

        from backend.repositories.alerts import insert_alert

        return await insert_alert(
            db,
            user_id=user_id,
            ticker=normalized_ticker,
            condition=normalized_condition,
            target_price=target_price,
            auto_analyze=auto_analyze,
            alert_type=normalized_alert_type,
            creation_source=normalized_source,
            creation_run_id=creation_run_id,
        )
    except AlertGuardrailViolation as exc:
        if not skip_if_limited:
            raise
        _logger.info(
            "Skipped AI alert user=%s ticker=%s source=%s reason=%s",
            user_id,
            normalized_ticker,
            normalized_source,
            exc.code,
        )
        return None


async def rearm_alert_with_guardrails(db: AsyncSession, alert: PriceAlert) -> PriceAlert:
    """Re-enable a manual UI alert without letting it bypass the active cap."""
    if alert.user_id is None:
        raise ValueError("Cannot re-arm an unowned alert")

    already_active = alert.enabled and alert.triggered_at is None
    if not already_active:
        settings = await _lock_user_settings(db, alert.user_id)
        await _enforce_active_cap(db, settings, alert.user_id, exclude_alert_id=alert.id)
    alert.enabled = True
    alert.triggered_at = None
    await db.flush()
    return alert
