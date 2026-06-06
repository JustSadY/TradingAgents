from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.agent_settings import AgentSetting

async def get_agent_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None):
    stmt = select(AgentSetting).where(AgentSetting.scope == scope)
    if scope == "user":
        stmt = stmt.where(AgentSetting.user_id == user_id)
    else:
        stmt = stmt.where(AgentSetting.user_id.is_(None))
    res = await db.execute(stmt)
    return res.scalars().all()

async def get_server_agent_settings(db: AsyncSession):
    return await get_agent_settings_by_scope(db, "server")

async def get_user_agent_settings(db: AsyncSession, user_id: int):
    return await get_agent_settings_by_scope(db, "user", user_id)
