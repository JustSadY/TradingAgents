from __future__ import annotations

from backend.models.agent_settings import AgentSetting
from backend.models.tool_settings import AgentToolSetting
from backend.repositories.agent_settings import get_runtime_agent_settings
from backend.repositories.tool_settings import get_runtime_tool_settings


async def test_runtime_scope_queries_return_server_and_current_user_only(db_session, test_user, admin_user) -> None:
    agent_key = "__runtime_scope_test_agent__"
    tool_key = "__runtime_scope_test_tool__"
    db_session.add_all(
        [
            AgentSetting(
                scope="server",
                user_id=None,
                agent_key=agent_key,
                enabled=False,
                settings={"source": "server"},
            ),
            AgentSetting(
                scope="user",
                user_id=test_user.id,
                agent_key=agent_key,
                enabled=True,
                settings={"source": "user"},
            ),
            AgentSetting(
                scope="user",
                user_id=admin_user.id,
                agent_key=agent_key,
                enabled=True,
                settings={"source": "other-user"},
            ),
            AgentToolSetting(
                scope="server",
                user_id=None,
                tool_key=tool_key,
                enabled=False,
                settings={"source": "server"},
            ),
            AgentToolSetting(
                scope="user",
                user_id=test_user.id,
                tool_key=tool_key,
                enabled=True,
                settings={"source": "user"},
            ),
            AgentToolSetting(
                scope="user",
                user_id=admin_user.id,
                tool_key=tool_key,
                enabled=True,
                settings={"source": "other-user"},
            ),
        ]
    )
    await db_session.flush()

    agent_rows = [
        row for row in await get_runtime_agent_settings(db_session, test_user.id) if row.agent_key == agent_key
    ]
    tool_rows = [
        row for row in await get_runtime_tool_settings(db_session, test_user.id) if row.tool_key == tool_key
    ]

    assert {(row.scope, row.user_id, row.settings["source"]) for row in agent_rows} == {
        ("server", None, "server"),
        ("user", test_user.id, "user"),
    }
    assert {(row.scope, row.user_id, row.settings["source"]) for row in tool_rows} == {
        ("server", None, "server"),
        ("user", test_user.id, "user"),
    }
