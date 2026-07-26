from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.preset import PresetApplyResponse, PresetCreate, PresetDeleteResponse, PresetRead
from backend.services import preset_service
from backend.services.preset_service import PresetError

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=list[PresetRead])
async def list_presets_run(
    user_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await preset_service.list_user_presets(db, user_id, current_user)
    except PresetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
    try:
        return await preset_service.create_user_preset(
            db, user_id, current_user, name=body.name, description=body.description, settings_json=body.settings_json
        )
    except PresetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
    try:
        await preset_service.delete_user_preset(db, user_id, current_user, preset_id)
    except PresetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
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
    try:
        preset_name = await preset_service.apply_user_preset(db, user_id, current_user, preset_id)
    except PresetError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"applied": True, "preset_name": preset_name}
