import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.repositories.permissions import get_user_setting_permission
from backend.repositories.users import get_user_by_id
from backend.schemas.preset import PresetApplyResponse, PresetCreate, PresetDeleteResponse, PresetRead

router = APIRouter(prefix="/api/presets", tags=["presets"])
_logger = logging.getLogger(__name__)


async def _resolve_target_user(user_id: int | None, current_user: User, db: AsyncSession) -> User:
    if user_id is not None and current_user.is_admin:
        target_user = await get_user_by_id(db, user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        return target_user
    return current_user


async def _check_presets_permission(user: User, db: AsyncSession, current_user: User):
    if current_user.is_admin:
        return
    perm = await get_user_setting_permission(db, user.id, "presets")
    if not perm or not perm.allowed:
        raise HTTPException(status_code=403, detail="You do not have permission to manage preset templates.")


@router.get("", response_model=list[PresetRead])
async def list_presets_run(
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.preset import list_presets as _repo_list

    target_user = await _resolve_target_user(user_id, current_user, db)
    return await _repo_list(db, user=target_user)


@router.post(
    "",
    response_model=PresetRead,
    responses={403: {"description": "Permission denied"}, 409: {"description": "Conflict"}},
)
async def create_preset_run(
    body: PresetCreate,
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = await _resolve_target_user(user_id, current_user, db)
    await _check_presets_permission(target_user, db, current_user)
    from backend.repositories.preset import create_preset as _repo_create
    from backend.repositories.preset import get_preset_by_name

    existing = await get_preset_by_name(db, body.name, target_user.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"A template named '{body.name}' already exists")

    return await _repo_create(
        db, user_id=target_user.id, name=body.name, description=body.description, settings_json=body.settings_json
    )


@router.delete(
    "/{preset_id}",
    response_model=PresetDeleteResponse,
    responses={403: {"description": "Permission denied"}, 404: {"description": "Template not found"}},
)
async def delete_preset(
    preset_id: int,
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = await _resolve_target_user(user_id, current_user, db)
    await _check_presets_permission(target_user, db, current_user)
    from backend.repositories.preset import get_preset_by_id

    preset = await get_preset_by_id(db, preset_id, user=target_user)
    if not preset:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(preset)
    return {"deleted": True}


@router.post(
    "/{preset_id}/apply",
    response_model=PresetApplyResponse,
    responses={
        403: {"description": "Permission denied"},
        404: {"description": "Template not found"},
        422: {"description": "Validation error"},
    },
)
async def apply_preset(
    preset_id: int,
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply a preset's settings to the target user's AppSettings row."""
    target_user = await _resolve_target_user(user_id, current_user, db)
    await _check_presets_permission(target_user, db, current_user)
    from backend.repositories.preset import get_preset_by_id
    from backend.services.settings_service import apply_preset_to_settings

    preset = await get_preset_by_id(db, preset_id, user=target_user)
    if not preset:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        preset_name = await apply_preset_to_settings(db, target_user, preset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"applied": True, "preset_name": preset_name}
