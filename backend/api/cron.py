from fastapi import APIRouter, Depends

from backend.api.deps import get_current_user
from backend.models.user import User
from backend.schemas.cron import CronStatusResponse
from backend.services.cron_service import get_cron_service

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/status", response_model=CronStatusResponse)
async def cron_status(user: User = Depends(get_current_user)) -> CronStatusResponse:
    cron = get_cron_service()
    if cron is None:
        return CronStatusResponse(running=False, job_configured=False, next_run_time=None)
    return CronStatusResponse.model_validate(cron.get_status(user_id=user.id))
