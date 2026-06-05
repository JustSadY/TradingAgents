"""Business logic for per-user application settings (``AppSettings``).

This module owns everything that used to live inside ``api/settings.py`` as
private helpers and was imported across the API and even from other services
(creating an ``api -> service`` dependency inversion). Routers and services now
depend on this service instead.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.schemas.settings import SettingsRead, SettingsUpdate


async def get_or_create_settings(
    db: AsyncSession, user=None,
) -> AppSettings:
    """Return the settings row for ``user`` (or the global row), creating it lazily."""
    user_id = getattr(user, "id", None) if user is not None else None
    if user_id is not None:
        result = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=user_id)
            db.add(settings)
            await db.flush()
        return settings
    result = await db.execute(select(AppSettings).where(AppSettings.user_id.is_(None)).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings()
        db.add(settings)
        await db.flush()
    return settings


def settings_to_read(settings: AppSettings) -> SettingsRead:
    """Map an ``AppSettings`` row to its read DTO (single source of truth)."""
    return SettingsRead(
        cron_enabled=settings.cron_enabled,
        cron_schedule=settings.cron_schedule,
        price_tolerance_pct=settings.price_tolerance_pct,
        watchlist=settings.watchlist,
        output_language=settings.output_language or "English",
        llm_provider=settings.llm_provider or "openai",
        llm_model=settings.llm_model or "gpt-4o-mini",
        investor_persona=settings.investor_persona or "conservative",
        analyst_concurrency_limit=settings.analyst_concurrency_limit or 1,
        max_recur_limit=settings.max_recur_limit or 1000,
        benchmark_ticker=settings.benchmark_ticker,
        max_debate_rounds=settings.max_debate_rounds,
        max_risk_rounds=settings.max_risk_rounds,
        max_position_size_pct=settings.max_position_size_pct,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        strict_stop_loss_mode=settings.strict_stop_loss_mode,
        node_retry_attempts=settings.node_retry_attempts or 2,
        node_retry_base_delay=settings.node_retry_base_delay or 1.0,
        include_historical_analyses=settings.include_historical_analyses,
        historical_analyses_limit=settings.historical_analyses_limit or 5,
        openai_reasoning_effort=settings.openai_reasoning_effort,
        anthropic_effort=settings.anthropic_effort,
        google_thinking_level=settings.google_thinking_level,
        webhook_url=settings.webhook_url,
        webhook_enabled=settings.webhook_enabled,
        webhook_events=settings.webhook_events or "analysis_complete",
        updated_at=settings.updated_at,
    )


async def apply_settings_update(
    db: AsyncSession, settings: AppSettings, body: SettingsUpdate,
) -> AppSettings:
    """Apply a partial settings update, reset the active preset on real changes,
    persist, and re-sync the user's cron job."""
    has_changes = False
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "active_preset_name":
            settings.active_preset_name = value
            continue
        if getattr(settings, field, None) != value:
            has_changes = True
        setattr(settings, field, value)
    if has_changes:
        # An explicit edit detaches the row from any named preset.
        settings.active_preset_name = None
    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await _resync_cron(settings)
    return settings


_settings_change_listener = None


def register_settings_change_listener(listener) -> None:
    """Register a callback to be notified when user settings are updated."""
    global _settings_change_listener
    _settings_change_listener = listener


async def _resync_cron(settings: AppSettings) -> None:
    if _settings_change_listener is not None:
        await _settings_change_listener(settings)
