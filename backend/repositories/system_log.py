from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.log import SystemLog
from backend.repositories.common import scope_to_user


async def list_user_logs(
    db: AsyncSession,
    user,
    level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SystemLog]:
    q = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).offset(offset)
    if level:
        q = q.where(SystemLog.level == level.upper())
    q = scope_to_user(q, SystemLog, user)
    result = await db.execute(q)
    return list(result.scalars().all())

async def list_all_logs(
    db: AsyncSession,
    level: str | None = None,
    source: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SystemLog]:
    q = select(SystemLog).order_by(desc(SystemLog.created_at)).limit(limit).offset(offset)
    if level:
        q = q.where(SystemLog.level == level.upper())
    if source:
        q = q.where(SystemLog.source == source)
    if user_id:
        q = q.where(SystemLog.user_id == user_id)
    result = await db.execute(q)
    return list(result.scalars().all())
