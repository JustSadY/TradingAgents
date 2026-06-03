"""Admin-only system settings API (cron, webhook)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.api.deps import require_admin, get_db
from backend.models.user import User
from backend.models.system_settings import SystemSettings
from backend.schemas.system_settings import SystemSettingsRead, SystemSettingsUpdate

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
    if body.cron_enabled is not None:
        ss.cron_enabled = body.cron_enabled
    if body.cron_schedule is not None:
        ss.cron_schedule = body.cron_schedule
    if body.watchlist is not None:
        ss.watchlist = body.watchlist
    if body.webhook_url is not None:
        ss.webhook_url = body.webhook_url
    if body.webhook_enabled is not None:
        ss.webhook_enabled = body.webhook_enabled
    if body.webhook_events is not None:
        ss.webhook_events = body.webhook_events

    # Re-apply cron job with new schedule
    try:
        from backend.services.cron_service import get_cron_service
        cron = get_cron_service()
        if cron:
            await cron.apply_settings(ss)
    except Exception:
        pass

    return ss
