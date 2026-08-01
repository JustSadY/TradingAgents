from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.log import SystemLog
from backend.repositories.system_log import list_all_logs, list_user_logs

async def get_user_logs(
    db: AsyncSession,
    user,
    level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SystemLog]:
    return await list_user_logs(db, user, level, limit, offset)

async def get_all_logs(
    db: AsyncSession,
    level: str | None = None,
    source: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SystemLog]:
    return await list_all_logs(db, level, source, user_id, limit, offset)
