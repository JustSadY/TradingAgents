import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.repositories.permissions import get_user_setting_permission
from backend.schemas.preset import PresetCreate, PresetRead

router = APIRouter(prefix="/api/presets", tags=["presets"])
_logger = logging.getLogger(__name__)


@router.get("", response_model=list[PresetRead])
async def list_presets_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.preset import list_presets as _repo_list

    return await _repo_list(db, user=current_user)


async def _check_presets_permission(user: User, db: AsyncSession):
    if user.is_admin:
        return
    perm = await get_user_setting_permission(db, user.id, "presets")
    if not perm or not perm.allowed:
        raise HTTPException(status_code=403, detail="You do not have permission to manage preset templates.")


@router.post("", response_model=PresetRead)
async def create_preset_run(
    body: PresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_presets_permission(current_user, db)
    from backend.repositories.preset import create_preset as _repo_create
    from backend.repositories.preset import get_preset_by_name

    existing = await get_preset_by_name(db, body.name, current_user.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"A template named '{body.name}' already exists")

    return await _repo_create(
        db, user_id=current_user.id, name=body.name, description=body.description, settings_json=body.settings_json
    )


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_presets_permission(current_user, db)
    from backend.repositories.preset import get_preset_by_id

    preset = await get_preset_by_id(db, preset_id, user=current_user)
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
    """Apply a preset's settings to the current user's AppSettings row."""
    await _check_presets_permission(current_user, db)
    from backend.repositories.preset import get_preset_by_id
    from backend.services.settings_service import apply_preset_to_settings

    preset = await get_preset_by_id(db, preset_id, user=current_user)
    if not preset:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        preset_name = await apply_preset_to_settings(db, current_user, preset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"applied": True, "preset_name": preset_name}
