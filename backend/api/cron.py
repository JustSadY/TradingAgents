from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.cron import CronStatusResponse
from backend.services.cron_service import get_cron_service

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/status", response_model=CronStatusResponse)
async def cron_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CronStatusResponse:
    cron = get_cron_service()
    if cron is None:
        return CronStatusResponse(
            running=False,
            job_configured=False,
            next_run_time=None,
            degraded_reason="scheduler_not_initialized",
        )
    return CronStatusResponse.model_validate(await cron.build_status(db, user_id=user.id))
