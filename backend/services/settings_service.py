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
    db: AsyncSession, settings: AppSettings, body: SettingsUpdate,
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

    settings.updated_at = datetime.now(timezone.utc)
    await db.flush()
    
    from backend.core.events import emit
    emit("settings_updated", settings=settings)
    
    return settings
