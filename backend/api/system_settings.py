from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, require_admin
from backend.models.user import User
from backend.schemas.system_settings import SystemSettingsRead, SystemSettingsUpdate
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate
from backend.services import system_settings_service

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])

@router.get("", response_model=SystemSettingsRead)
async def get_system_settings(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await system_settings_service.get_or_create_system_settings(db)

@router.put("", response_model=SystemSettingsRead)
async def update_system_settings(
    body: SystemSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    fields = body.model_dump(exclude_unset=True)
    if {"trading_mode", "active_broker"}.intersection(fields) and not current_user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Server Owner can configure a brokerage execution mode.",
        )
    try:
        return await system_settings_service.update_system_settings(db, fields)
    except system_settings_service.InvalidTradingConfiguration as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.get("/tools", response_model=ToolSettingsRead)
async def get_server_tools(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_settings_service import get_server_tool_settings

    return await get_server_tool_settings(db)

@router.put("/tools", response_model=ToolSettingsRead)
async def update_server_tools(
    body: ToolSettingsUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.tool_settings_service import apply_server_tool_settings_update

    return await apply_server_tool_settings_update(db, body)
