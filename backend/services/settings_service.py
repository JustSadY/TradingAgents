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
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings
from backend.schemas.settings import SettingsRead, SettingsUpdate

_logger = logging.getLogger(__name__)


class SettingsPermissionError(PermissionError):
    pass


def _enforce_auto_execution_safety(settings: AppSettings, fields: dict) -> None:
    """Make automatic AI execution impossible without deterministic safeguards.

    ``auto_execute_signals`` is an opt-in to unattended execution, not an opt-out
    from the stability controller or run-quality gate.  Keep the stored settings
    self-consistent so every execution path observes the same contract, including
    presets and background scheduler runs.
    """
    auto_execute = bool(fields.get("auto_execute_signals", getattr(settings, "auto_execute_signals", False)))
    if not auto_execute:
        return
    fields["quality_gate_enabled"] = True
    fields["decision_stability_mode"] = "enforce"


async def enforce_settings_update_permissions(db: AsyncSession, user, body: SettingsUpdate) -> None:
    """Validate which settings sections a non-admin user may mutate."""
    from backend.models.page_permission import SECTION_FIELDS
    from backend.repositories.permissions import list_allowed_setting_sections

    allowed_sections = await list_allowed_setting_sections(db, user.id)
    attempted = body.model_dump(exclude_unset=True)

    if "max_recur_limit" in attempted:
        raise SettingsPermissionError("Advanced engine settings can only be modified by administrators.")

    mapped_fields = {field for fields in SECTION_FIELDS.values() for field in fields}
    unmapped = set(attempted) - mapped_fields
    if unmapped:
        raise SettingsPermissionError(
            f"No permission section is configured for settings: {', '.join(sorted(unmapped))}"
        )

    for section, fields in SECTION_FIELDS.items():
        if any(field in attempted for field in fields) and section not in allowed_sections:
            raise SettingsPermissionError(f"You do not have permission to modify settings in section: {section}")


def parse_preset_settings_json(settings_json: str) -> SettingsUpdate:
    """Parse a stored preset as a strict, validated ``SettingsUpdate``.

    ``SettingsUpdate`` deliberately accepts partial updates, but Pydantic's
    default extra-field behaviour is permissive. Check field names first so
    an ORM attribute such as ``user_id`` cannot reappear as a mass-assignment
    path through a legacy or manually-created preset.
    """
    try:
        data = json.loads(settings_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Preset settings must be valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Preset settings must be a JSON object")

    allowed_fields = set(SettingsUpdate.model_fields)
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
    from backend.core.log_redaction import register_sensitive_literal
    from backend.repositories.settings import get_or_create_app_settings

    user_id = getattr(user, "id", None) if user is not None else None
    settings = await get_or_create_app_settings(db, user_id)

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
    _enforce_auto_execution_safety(settings, fields)
    webhook_url = fields.get("webhook_url")
    if webhook_url:
        from backend.services.notification_service import resolve_webhook_target

        await resolve_webhook_target(webhook_url)
    for field, value in fields.items():
        if getattr(settings, field, None) != value:
            has_changes = True
        setattr(settings, field, value)
    if has_changes:
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
        from backend.services.notification_service import resolve_webhook_target

        await resolve_webhook_target(webhook_url)

    settings = await get_or_create_settings(db, user)
    _enforce_auto_execution_safety(settings, fields)
    for key, value in fields.items():
        setattr(settings, key, value)
    settings.active_preset_name = preset.name
    settings.updated_at = datetime.now(UTC)

    if settings.webhook_url:
        from backend.core.log_redaction import register_sensitive_literal

        register_sensitive_literal(settings.webhook_url)

    await db.flush()
    await db.commit()

    from backend.core.events import emit

    try:
        await emit("settings_updated", settings=settings)
    except Exception:
        _logger.warning("Preset settings update event emission failed", exc_info=True)
    return preset.name


async def add_ticker_to_watchlist(db: AsyncSession, user, ticker: str) -> list[str]:
    """Add a normalized ticker while enforcing the global watchlist limit."""
    normalized = ticker.strip().upper()
    settings = await get_or_create_settings(db, user)
    current = list(settings.watchlist or [])
    if normalized in current:
        return current
    if len(current) >= 100:
        raise ValueError("watchlist cannot contain more than 100 symbols")
    settings.watchlist = [*current, normalized]
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
