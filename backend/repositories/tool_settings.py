from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import AgentToolSetting
from backend.repositories.common import get_settings_by_scope_generic


async def get_tool_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None):
    return await get_settings_by_scope_generic(db, AgentToolSetting, scope, user_id)


async def get_server_tool_settings(db: AsyncSession):
    return await get_tool_settings_by_scope(db, "server")


async def get_user_tool_settings(db: AsyncSession, user_id: int):
    return await get_tool_settings_by_scope(db, "user", user_id)


async def get_runtime_tool_settings(db: AsyncSession, user_id: int | None):
    """Load server and optional user tool-setting scopes in one round-trip."""
    if user_id is None:
        return await get_server_tool_settings(db)

    stmt = select(AgentToolSetting).where(
        or_(
            and_(AgentToolSetting.scope == "server", AgentToolSetting.user_id.is_(None)),
            and_(AgentToolSetting.scope == "user", AgentToolSetting.user_id == user_id),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def ensure_tool_setting(
    db: AsyncSession,
    *,
    row: AgentToolSetting | None,
    scope: str,
    user_id: int | None,
    tool_key: str,
    default_enabled: bool,
) -> AgentToolSetting:
    """Return an existing tool-setting row or create its canonical scoped row."""
    if row is not None:
        return row
    row = AgentToolSetting(
        scope=scope,
        user_id=user_id if scope == "user" else None,
        tool_key=tool_key,
        enabled=default_enabled,
        settings={},
    )
    db.add(row)
    return row
