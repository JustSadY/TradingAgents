from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.log import LogRead
from backend.services.system_log_service import get_all_logs, get_user_logs

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/me", response_model=list[LogRead])
async def list_my_logs(
    level: str | None = Query(default=None, description="Filter by level: INFO, WARNING, ERROR, CRITICAL"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_user_logs(db, current_user, level, limit, offset)


@router.get("", response_model=list[LogRead])
async def list_logs(
    level: str | None = Query(default=None, description="Filter by level: INFO, WARNING, ERROR, CRITICAL"),
    source: str | None = Query(default=None),
    user_id: int | None = Query(default=None, description="Filter by user ID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await get_all_logs(db, level, source, user_id, limit, offset)
