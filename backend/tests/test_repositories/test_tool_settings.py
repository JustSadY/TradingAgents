from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tool_settings import AgentToolSetting
from backend.repositories.tool_settings import get_server_tool_settings, get_user_tool_settings


@pytest.fixture
async def server_tool_setting(db: AsyncSession) -> AgentToolSetting:
    setting = AgentToolSetting(
        scope="server",
        user_id=None,
        tool_key="test_tool",
        enabled=True,
        settings={"api_key": "server-key"},
    )
    db.add(setting)
    await db.flush()
    return setting

@pytest.fixture
async def user_tool_setting(db: AsyncSession, test_user) -> AgentToolSetting:
    setting = AgentToolSetting(
        scope="user",
        user_id=test_user.id,
        tool_key="test_tool",
        enabled=True,
        settings={"api_key": "user-key"},
    )
    db.add(setting)
    await db.flush()
    return setting

class TestToolSettingsRepository:
    async def test_get_server_tool_settings(self, db: AsyncSession, server_tool_setting: AgentToolSetting):
        results = await get_server_tool_settings(db)
        assert len(results) == 1
        assert results[0].tool_key == "test_tool"
        assert results[0].settings["api_key"] == "server-key"

    async def test_get_server_tool_settings_empty(self, db: AsyncSession):
        results = await get_server_tool_settings(db)
        assert len(results) == 0

    async def test_get_user_tool_settings(self, db: AsyncSession, user_tool_setting: AgentToolSetting, test_user):
        results = await get_user_tool_settings(db, test_user.id)
        assert len(results) == 1
        assert results[0].tool_key == "test_tool"
        assert results[0].settings["api_key"] == "user-key"

    async def test_get_user_tool_settings_scoped(self, db: AsyncSession, user_tool_setting: AgentToolSetting):
        results = await get_user_tool_settings(db, 99999)
        assert len(results) == 0

    async def test_get_user_tool_settings_multiple(self, db: AsyncSession, test_user):
        for tool in ["tool_a", "tool_b", "tool_c"]:
            db.add(
                AgentToolSetting(
                    scope="user",
                    user_id=test_user.id,
                    tool_key=tool,
                    enabled=True,
                )
            )
        await db.flush()

        results = await get_user_tool_settings(db, test_user.id)
        assert len(results) == 3
        keys = {r.tool_key for r in results}
        assert keys == {"tool_a", "tool_b", "tool_c"}

    async def test_get_user_tool_settings_does_not_include_server(
        self, db: AsyncSession, server_tool_setting: AgentToolSetting, test_user
    ):
        results = await get_user_tool_settings(db, test_user.id)
        assert len(results) == 0
