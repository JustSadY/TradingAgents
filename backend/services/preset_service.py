"""Config preset (template) service — save/apply/delete a user's settings snapshots."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.preset import ConfigPreset
from backend.models.user import User
from backend.repositories.permissions import get_user_setting_permission
from backend.repositories.users import get_user_by_id
from backend.schemas.settings import SettingsUpdate

class PresetError(Exception):
    """Raised for client-correctable problems (missing user/template, no
    permission, name conflict) — the API layer translates ``status_code``
    into an ``HTTPException``, keeping FastAPI/HTTP concerns out of the
    service."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code

async def resolve_target_user(db: AsyncSession, user_id: int | None, current_user: User) -> User:
    if user_id is not None and current_user.is_admin:
        target_user = await get_user_by_id(db, user_id)
        if not target_user:
            raise PresetError("User not found", status_code=404)
        return target_user
    return current_user

async def _check_presets_permission(db: AsyncSession, user: User, current_user: User) -> None:
    if current_user.is_admin:
        return
    perm = await get_user_setting_permission(db, user.id, "presets")
    if not perm or not perm.allowed:
        raise PresetError("You do not have permission to manage preset templates.", status_code=403)

async def _check_preset_settings_permissions(
    db: AsyncSession,
    user: User,
    current_user: User,
    update: SettingsUpdate,
) -> None:
    """Apply the same deny-by-default field policy used by ``PUT /settings``.

    Permission to manage a preset is not permission to modify every setting
    through that preset.  Without this check, the preset endpoint bypasses
    per-section RBAC even when the direct settings endpoint is protected.
    """
    if current_user.is_admin:
        return

    from backend.models.page_permission import SECTION_FIELDS
    from backend.repositories.permissions import list_allowed_setting_sections

    attempted = set(update.model_fields_set)
    advanced_fields = {"max_recur_limit"}
    if attempted & advanced_fields:
        raise PresetError("Advanced engine settings can only be modified by administrators.", status_code=403)

    mapped_fields = {field for fields in SECTION_FIELDS.values() for field in fields}
    unmapped = attempted - mapped_fields
    if unmapped:
        raise PresetError(
            f"No permission section is configured for settings: {', '.join(sorted(unmapped))}", status_code=403
        )

    allowed_sections = await list_allowed_setting_sections(db, user.id)
    for section, fields in SECTION_FIELDS.items():
        if attempted.intersection(fields) and section not in allowed_sections:
            raise PresetError(f"You do not have permission to modify settings in section: {section}", status_code=403)

async def list_user_presets(db: AsyncSession, user_id: int | None, current_user: User) -> list[ConfigPreset]:
    from backend.repositories.preset import list_presets

    target_user = await resolve_target_user(db, user_id, current_user)
    return await list_presets(db, user=target_user)

async def create_user_preset(
    db: AsyncSession,
    user_id: int | None,
    current_user: User,
    *,
    name: str,
    description: str,
    settings_json: str,
) -> ConfigPreset:
    from backend.repositories.preset import create_preset, get_preset_by_name
    from backend.services.settings_service import parse_preset_settings_json, serialize_preset_settings

    target_user = await resolve_target_user(db, user_id, current_user)
    await _check_presets_permission(db, target_user, current_user)
    try:
        update = parse_preset_settings_json(settings_json)
    except ValueError as exc:
        raise PresetError(str(exc), status_code=422) from exc
    await _check_preset_settings_permissions(db, target_user, current_user, update)

    existing = await get_preset_by_name(db, name, target_user.id)
    if existing:
        raise PresetError(f"A template named '{name}' already exists", status_code=409)

    return await create_preset(
        db,
        user_id=target_user.id,
        name=name,
        description=description,
        settings_json=serialize_preset_settings(update),
    )

async def delete_user_preset(db: AsyncSession, user_id: int | None, current_user: User, preset_id: int) -> None:
    from backend.repositories.preset import get_preset_by_id

    target_user = await resolve_target_user(db, user_id, current_user)
    await _check_presets_permission(db, target_user, current_user)

    preset = await get_preset_by_id(db, preset_id, user=target_user)
    if not preset:
        raise PresetError("Template not found", status_code=404)
    await db.delete(preset)

async def apply_user_preset(db: AsyncSession, user_id: int | None, current_user: User, preset_id: int) -> str:
    """Apply a preset's settings to the target user's AppSettings row. Returns the preset name."""
    from backend.repositories.preset import get_preset_by_id
    from backend.services.settings_service import apply_preset_to_settings, parse_preset_settings_json

    target_user = await resolve_target_user(db, user_id, current_user)
    await _check_presets_permission(db, target_user, current_user)

    preset = await get_preset_by_id(db, preset_id, user=target_user)
    if not preset:
        raise PresetError("Template not found", status_code=404)
    try:
        update = parse_preset_settings_json(preset.settings_json)
        await _check_preset_settings_permissions(db, target_user, current_user, update)
        return await apply_preset_to_settings(db, target_user, preset)
    except ValueError as exc:
        raise PresetError(str(exc), status_code=422) from exc
