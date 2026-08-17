from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_settings import AgentSetting
from backend.repositories.common import get_settings_by_scope_generic


async def get_agent_settings_by_scope(db: AsyncSession, scope: str, user_id: int | None = None):
    return await get_settings_by_scope_generic(db, AgentSetting, scope, user_id)


async def get_server_agent_settings(db: AsyncSession):
    return await get_agent_settings_by_scope(db, "server")


async def get_user_agent_settings(db: AsyncSession, user_id: int):
    return await get_agent_settings_by_scope(db, "user", user_id)


def persist_agent_setting(
    db: AsyncSession,
    *,
    row: AgentSetting | None,
    scope: str,
    user_id: int | None,
    agent_key: str,
    enabled: bool | None,
    settings: dict[str, Any],
) -> AgentSetting:
    """Create or update one agent-setting ORM row without leaking persistence into services."""
    if row is None:
        row = AgentSetting(
            scope=scope,
            user_id=user_id if scope == "user" else None,
            agent_key=agent_key,
            enabled=enabled,
            settings=settings,
        )
        db.add(row)
        return row

    row.enabled = enabled
    row.settings = settings
    return row
