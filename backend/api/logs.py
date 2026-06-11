from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.core.database import get_db
from backend.models.log import SystemLog
from backend.models.user import User
from backend.schemas.log import LogRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/me", response_model=list[LogRead])
async def list_my_logs(
    level: str | None = Query(default=None, description="Filter by level: INFO, WARNING, ERROR, CRITICAL"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.common import scope_to_user

    q = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).offset(offset)
    if level:
        q = q.where(SystemLog.level == level.upper())
    q = scope_to_user(q, SystemLog, current_user)
    result = await db.execute(q)
    return result.scalars().all()


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
    q = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).offset(offset)
    if level:
        q = q.where(SystemLog.level == level.upper())
    if source:
        q = q.where(SystemLog.source == source)
    if user_id:
        q = q.where(SystemLog.user_id == user_id)
    result = await db.execute(q)
    return result.scalars().all()

