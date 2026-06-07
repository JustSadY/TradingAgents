"""Business logic for per-user application settings (``AppSettings``).

This module owns everything that used to live inside ``api/settings.py`` as
private helpers and was imported across the API and even from other services
(creating an ``api -> service`` dependency inversion). Routers and services now
depend on this service instead.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.schemas.settings import SettingsRead, SettingsUpdate


async def get_or_create_settings(
    db: AsyncSession,
    user=None,
) -> AppSettings:
    """Return the settings row for ``user`` (or the global row), creating it lazily."""
    user_id = getattr(user, "id", None) if user is not None else None

    from backend.core.log_redaction import register_sensitive_literal

    if user_id is not None:
        result = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppSettings(user_id=user_id)
            db.add(settings)
            await db.flush()

        if settings.webhook_url:
            register_sensitive_literal(settings.webhook_url)
        return settings

    result = await db.execute(select(AppSettings).where(AppSettings.user_id.is_(None)).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AppSettings()
        db.add(settings)
        await db.flush()

    if settings.webhook_url:
        register_sensitive_literal(settings.webhook_url)
    return settings


def settings_to_read(settings: AppSettings) -> SettingsRead:
    """Map an ``AppSettings`` row to its read DTO (single source of truth)."""
    # Using Pydantic's from_attributes=True (configured in SettingsRead)
    # allows us to directly validate the SQLAlchemy model instance.
    return SettingsRead.model_validate(settings)


async def apply_settings_update(
    db: AsyncSession,
    settings: AppSettings,
    body: SettingsUpdate,
) -> AppSettings:
    """Apply a partial settings update, reset the active preset on real changes,
    persist, and emit a 'settings_updated' event."""
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

    if settings.webhook_url:
        from backend.core.log_redaction import register_sensitive_literal

        register_sensitive_literal(settings.webhook_url)

    settings.updated_at = datetime.now(UTC)
    await db.flush()

    from backend.core.events import emit

    emit("settings_updated", settings=settings)

    return settings


async def get_user_language(db: AsyncSession, user=None) -> str:
    """Return the preferred output language for a user (fallback to English)."""
    if user is None:
        return "English"
    try:
        settings = await get_or_create_settings(db, user)
        return settings.output_language or "English"
    except Exception:
        return "English"


async def apply_preset_to_settings(db: AsyncSession, user, preset) -> str:
    """Apply a preset's settings JSON onto *user*'s AppSettings row.

    Raises ValueError if the stored preset JSON is invalid. Flushes so any
    constraint error surfaces here rather than at request-commit time.
    """
    try:
        data = json.loads(preset.settings_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Template JSON invalid") from exc

    settings = await get_or_create_settings(db, user)
    for key, value in data.items():
        if hasattr(settings, key) and value is not None:
            setattr(settings, key, value)
    settings.active_preset_name = preset.name
    await db.flush()
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
