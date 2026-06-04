import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.core.database import get_db
from backend.api.deps import get_current_user
from backend.models.preset import ConfigPreset
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.preset import PresetCreate, PresetRead
from backend.api.settings import _get_or_create_settings
router = APIRouter(prefix="/api/presets", tags=["presets"])
_logger = logging.getLogger(__name__)
@router.get("", response_model=list[PresetRead])
async def list_presets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(ConfigPreset).order_by(ConfigPreset.created_at.desc())
    if not current_user.is_admin:
        q = q.where(ConfigPreset.user_id == current_user.id)
    result = await db.execute(q)
    return result.scalars().all()
async def _check_presets_permission(user: User, db: AsyncSession):
    if user.is_admin:
        return
    from backend.models.page_permission import UserSettingPermission
    result = await db.execute(
        select(UserSettingPermission)
        .where(UserSettingPermission.user_id == user.id)
        .where(UserSettingPermission.setting_key == "presets")
        .where(UserSettingPermission.allowed == True)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You do not have permission to manage preset templates.")
@router.post("", response_model=PresetRead)
async def create_preset(
    body: PresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_presets_permission(current_user, db)
    existing = await db.execute(
        select(ConfigPreset)
        .where(ConfigPreset.name == body.name)
        .where(ConfigPreset.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"'{body.name}' adında şablon zaten var")
    preset = ConfigPreset(
        name=body.name,
        description=body.description,
        settings_json=body.settings_json,
        user_id=current_user.id,
    )
    db.add(preset)
    await db.flush()
    return preset
@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_presets_permission(current_user, db)
    q = select(ConfigPreset).where(ConfigPreset.id == preset_id)
    if not current_user.is_admin:
        q = q.where(ConfigPreset.user_id == current_user.id)
    result = await db.execute(q)
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    await db.delete(preset)
    return {"deleted": True}
@router.post("/{preset_id}/apply")
async def apply_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_presets_permission(current_user, db)
    """Apply a preset's settings to the current user's AppSettings row."""
    q = select(ConfigPreset).where(ConfigPreset.id == preset_id)
    if not current_user.is_admin:
        q = q.where(ConfigPreset.user_id == current_user.id)
    result = await db.execute(q)
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    settings = await _get_or_create_settings(db, current_user)
    try:
        data = json.loads(preset.settings_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Şablon JSON geçersiz")
    for key, value in data.items():
        if hasattr(settings, key) and value is not None:
            if key in ("watchlist", "selected_analysts"):
                setattr(settings, key, value)
            else:
                setattr(settings, key, value)
    settings.active_preset_name = preset.name
    return {"applied": True, "preset_name": preset.name}
