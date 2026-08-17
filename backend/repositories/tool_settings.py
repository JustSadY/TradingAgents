from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import AgentToolSetting
from backend.repositories.common import get_settings_by_scope_generic


async def get_tool_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None):
    return await get_settings_by_scope_generic(db, AgentToolSetting, scope, user_id)


async def get_server_tool_settings(db: AsyncSession):
    return await get_tool_settings_by_scope(db, "server")


async def get_user_tool_settings(db: AsyncSession, user_id: int):
    return await get_tool_settings_by_scope(db, "user", user_id)


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
