from datetime import UTC

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, require_admin
from backend.models.system_settings import SystemSettings
from backend.models.user import User
from backend.schemas.system_settings import SystemSettingsRead, SystemSettingsUpdate
from backend.schemas.tool_settings import ToolSettingsRead, ToolSettingsUpdate

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])


async def _get_or_create_system_settings(db: AsyncSession) -> SystemSettings:
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    ss = result.scalar_one_or_none()
    if ss is None:
        ss = SystemSettings(id=1)
        db.add(ss)
        await db.flush()
    return ss


@router.get("", response_model=SystemSettingsRead)
async def get_system_settings(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _get_or_create_system_settings(db)


@router.put("", response_model=SystemSettingsRead)
async def update_system_settings(
    body: SystemSettingsUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ss = await _get_or_create_system_settings(db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ss, field, value)

    from datetime import datetime

    ss.updated_at = datetime.now(UTC)
    await db.flush()
    return ss


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
