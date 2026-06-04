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
    if body.searxng_url is not None:
        ss.searxng_url = body.searxng_url
    if body.reddit_client_id is not None:
        ss.reddit_client_id = body.reddit_client_id
    if body.reddit_client_secret is not None:
        ss.reddit_client_secret = body.reddit_client_secret
    if body.reddit_user_agent is not None:
        ss.reddit_user_agent = body.reddit_user_agent
    if body.alpha_vantage_api_key is not None:
        ss.alpha_vantage_api_key = body.alpha_vantage_api_key
    return ss
