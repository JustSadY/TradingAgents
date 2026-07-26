"""Business logic for per-user application settings (``AppSettings``).

This module owns everything that used to live inside ``api/settings.py`` as
private helpers and was imported across the API and even from other services
(creating an ``api -> service`` dependency inversion). Routers and services now
depend on this service instead.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.schemas.settings import SettingsRead, SettingsUpdate

_logger = logging.getLogger(__name__)

# A preset is a snapshot of editable application settings, not an ORM object
# dump.  In particular, ids/owners/timestamps and the active-preset marker may
# never be restored from user-supplied JSON.
_PRESET_EXCLUDED_FIELDS = frozenset({"active_preset_name"})


def parse_preset_settings_json(settings_json: str) -> SettingsUpdate:
    """Parse a stored preset as a strict, validated ``SettingsUpdate``.

    ``SettingsUpdate`` deliberately accepts partial updates, but Pydantic's
    default extra-field behaviour is permissive.  Check field names first so
    an ORM attribute such as ``user_id`` cannot reappear as a mass-assignment
    path through a legacy or manually-created preset.
    """
    try:
        data = json.loads(settings_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Preset settings must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Preset settings must be a JSON object")

    allowed_fields = set(SettingsUpdate.model_fields) - _PRESET_EXCLUDED_FIELDS
    unknown = set(data) - allowed_fields
    if unknown:
        raise ValueError(f"Preset contains unsupported settings: {', '.join(sorted(unknown))}")

    try:
        return SettingsUpdate.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Preset settings are invalid: {exc}") from exc


def serialize_preset_settings(update: SettingsUpdate) -> str:
    """Store only the validated fields of a preset in a canonical form."""
    return json.dumps(update.model_dump(exclude_unset=True), separators=(",", ":"), sort_keys=True)


async def get_or_create_settings(
    db: AsyncSession,
    user=None,
) -> AppSettings:
    """Return the settings row for ``user`` (or the global row), creating it lazily."""
    user_id = getattr(user, "id", None) if user is not None else None

    from backend.core.log_redaction import register_sensitive_literal

    where_clause = AppSettings.user_id == user_id if user_id is not None else AppSettings.user_id.is_(None)
    result = await db.execute(select(AppSettings).where(where_clause).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        # The database has a unique owner key, but two first requests for the
        # same account can still race between the SELECT above and INSERT.
        # Use a savepoint so a duplicate key does not roll back unrelated work
        # already pending in the caller's session; load the row the winner made.
        try:
            async with db.begin_nested():
                created = AppSettings(user_id=user_id)
                db.add(created)
                await db.flush()
            settings = created
        except IntegrityError:
            result = await db.execute(select(AppSettings).where(where_clause).limit(1))
            settings = result.scalar_one()

    if settings.webhook_url:
        register_sensitive_literal(settings.webhook_url)
    return settings


def settings_to_read(settings: AppSettings) -> SettingsRead:
    """Map an ``AppSettings`` row to its read DTO (single source of truth)."""
    return SettingsRead.model_validate(settings)


async def apply_settings_update(
    db: AsyncSession,
    settings: AppSettings,
    body: SettingsUpdate,
) -> AppSettings:
    """Apply a partial settings update, reset the active preset on real changes,
    persist, and emit a 'settings_updated' event."""
    has_changes = False
    fields = body.model_dump(exclude_unset=True)
    webhook_url = fields.get("webhook_url")
    if webhook_url:
        # Keep this at the service boundary as well as the HTTP route.  Preset
        # imports, admin/internal callers and future routes must not turn a
        # stored webhook setting into an SSRF primitive by bypassing the API
        # helper.
        from backend.services.notification_service import validate_webhook_url

        await validate_webhook_url(webhook_url)
    explicit_preset_name = "active_preset_name" in fields
    for field, value in fields.items():
        if field == "active_preset_name":
            settings.active_preset_name = value
            continue
        if getattr(settings, field, None) != value:
            has_changes = True
        setattr(settings, field, value)
    if has_changes and not explicit_preset_name:
        settings.active_preset_name = None

    if settings.webhook_url:
        from backend.core.log_redaction import register_sensitive_literal

        register_sensitive_literal(settings.webhook_url)

    settings.updated_at = datetime.now(UTC)
    await db.flush()
    await db.commit()

    from backend.core.events import emit

    try:
        await emit("settings_updated", settings=settings)
    except Exception:
        _logger.warning("Settings update event emission failed", exc_info=True)

    return settings


async def get_user_language(db: AsyncSession, user=None) -> str:
    """Return the preferred output language for a user (fallback to English)."""
    if user is None:
        return "English"
    try:
        settings = await get_or_create_settings(db, user)
        return settings.output_language or "English"
    except Exception as exc:
        _logger.warning("Could not load language preference for user %s: %s", getattr(user, "id", "?"), exc)
        return "English"


async def apply_preset_to_settings(db: AsyncSession, user, preset) -> str:
    """Apply a preset's settings JSON onto *user*'s AppSettings row.

    Raises ValueError if the stored preset JSON is invalid. Flushes so any
    constraint error surfaces here rather than at request-commit time.
    """
    update = parse_preset_settings_json(preset.settings_json)
    fields = update.model_dump(exclude_unset=True)

    webhook_url = fields.get("webhook_url")
    if webhook_url:
        from backend.services.notification_service import validate_webhook_url

        await validate_webhook_url(webhook_url)

    settings = await get_or_create_settings(db, user)
    for key, value in fields.items():
        # ``parse_preset_settings_json`` has already restricted this list to
        # SettingsUpdate fields.  Keep the None skip from legacy behaviour so
        # a nullable PATCH field cannot violate a non-null model column.
        if value is not None:
            setattr(settings, key, value)
    settings.active_preset_name = preset.name
    settings.updated_at = datetime.now(UTC)

    if settings.webhook_url:
        from backend.core.log_redaction import register_sensitive_literal

        register_sensitive_literal(settings.webhook_url)

    await db.flush()
    # Keep event consumers (notably the cron scheduler) from observing stale
    # settings in a different session.  This mirrors apply_settings_update.
    await db.commit()

    from backend.core.events import emit

    try:
        await emit("settings_updated", settings=settings)
    except Exception:
        _logger.warning("Preset settings update event emission failed", exc_info=True)
    return preset.name


async def add_ticker_to_watchlist(db: AsyncSession, user, ticker: str) -> list[str]:
    """Add ``ticker`` (already validated/normalized) to ``user``'s watchlist."""
    settings = await get_or_create_settings(db, user)
    if ticker not in settings.watchlist:
        settings.watchlist = [*settings.watchlist, ticker]
    await db.flush()
    return settings.watchlist


async def remove_ticker_from_watchlist(db: AsyncSession, user, ticker: str) -> list[str]:
    """Remove ``ticker`` from ``user``'s watchlist."""
    settings = await get_or_create_settings(db, user)
    settings.watchlist = [t for t in settings.watchlist if t != ticker]
    await db.flush()
    return settings.watchlist


async def get_webhook_deliveries(db: AsyncSession, user_id: int, limit: int = 20):
    from backend.repositories.webhook_delivery import list_webhook_deliveries

    return await list_webhook_deliveries(db, user_id, limit)
