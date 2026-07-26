"""Config preset (template) service — save/apply/delete a user's settings snapshots."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.preset import ConfigPreset
from backend.models.user import User
from backend.repositories.permissions import get_user_setting_permission
from backend.repositories.users import get_user_by_id


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

    target_user = await resolve_target_user(db, user_id, current_user)
    await _check_presets_permission(db, target_user, current_user)

    existing = await get_preset_by_name(db, name, target_user.id)
    if existing:
        raise PresetError(f"A template named '{name}' already exists", status_code=409)

    return await create_preset(
        db, user_id=target_user.id, name=name, description=description, settings_json=settings_json
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
    from backend.services.settings_service import apply_preset_to_settings

    target_user = await resolve_target_user(db, user_id, current_user)
    await _check_presets_permission(db, target_user, current_user)

    preset = await get_preset_by_id(db, preset_id, user=target_user)
    if not preset:
        raise PresetError("Template not found", status_code=404)
    try:
        return await apply_preset_to_settings(db, target_user, preset)
    except ValueError as exc:
        raise PresetError(str(exc), status_code=422) from exc
