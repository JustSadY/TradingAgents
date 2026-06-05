import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.api.deps import get_current_user
from backend.models.preset import ConfigPreset
from backend.models.user import User
from backend.schemas.preset import PresetCreate, PresetRead
from backend.services.settings_service import get_or_create_settings
from backend.repositories.common import scope_to_user
from backend.repositories.permissions import get_user_setting_permission
router = APIRouter(prefix="/api/presets", tags=["presets"])
_logger = logging.getLogger(__name__)
@router.get("", response_model=list[PresetRead])
async def list_presets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(ConfigPreset).order_by(ConfigPreset.created_at.desc())
    q = scope_to_user(q, ConfigPreset, current_user)
    result = await db.execute(q)
    return result.scalars().all()
async def _check_presets_permission(user: User, db: AsyncSession):
    if user.is_admin:
        return
    perm = await get_user_setting_permission(db, user.id, "presets")
    if not perm or not perm.allowed:
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
        raise HTTPException(status_code=409, detail=f"A template named '{body.name}' already exists")
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
    q = scope_to_user(q, ConfigPreset, current_user)
    result = await db.execute(q)
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Template not found")
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
    q = scope_to_user(q, ConfigPreset, current_user)
    result = await db.execute(q)
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Template not found")
    settings = await get_or_create_settings(db, current_user)
    try:
        data = json.loads(preset.settings_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Template JSON invalid")
    for key, value in data.items():
        if hasattr(settings, key) and value is not None:
            if key == "selected_analysts" and not current_user.is_admin:
                from backend.services.tool_access_service import get_user_agent_access
                agent_access_map = await get_user_agent_access(db, current_user.id)
                value = [
                    a for a in value
                    if agent_access_map.get(a, True)
                ]
            setattr(settings, key, value)
    settings.active_preset_name = preset.name
    return {"applied": True, "preset_name": preset.name}
