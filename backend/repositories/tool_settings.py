from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import AgentToolSetting


async def get_tool_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None):
    stmt = select(AgentToolSetting).where(AgentToolSetting.scope == scope)
    if scope == "user":
        stmt = stmt.where(AgentToolSetting.user_id == user_id)
    else:
        stmt = stmt.where(AgentToolSetting.user_id.is_(None))
    res = await db.execute(stmt)
    return res.scalars().all()


async def get_server_tool_settings(db: AsyncSession):
    return await get_tool_settings_by_scope(db, "server")


async def get_user_tool_settings(db: AsyncSession, user_id: int):
    return await get_tool_settings_by_scope(db, "user", user_id)
