from __future__ import annotations

from types import SimpleNamespace

from backend.services.tool_settings_service import get_user_tool_settings, registry


class _Tool:
    def __init__(self, key: str, analyst: str) -> None:
        self.key = key
        self.allowed_analysts = [analyst]
        self.default_enabled = True
        self.settings_schema = []

    def default_settings(self, *, scope: str) -> dict:
        assert scope == "user"
        return {}


async def test_user_tool_settings_builds_agent_hierarchy_once_for_all_tools(monkeypatch) -> None:
    context_calls = 0

    async def fake_rows(_db, _user_id):
        return []

    async def fake_context(_db, user_id):
        nonlocal context_calls
        assert user_id == 7
        context_calls += 1
        return {"market": {"enabled": True}, "news": {"enabled": True}}

    class FakeHierarchy:
        def __init__(self, context):
            self.context = context

        def is_enabled(self, agent_key: str) -> bool:
            return bool(self.context.get(agent_key, {}).get("enabled", True))

    monkeypatch.setattr("backend.repositories.tool_settings.get_user_tool_settings", fake_rows)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_context)
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", FakeHierarchy)
    monkeypatch.setattr(registry, "list", lambda: [_Tool("first", "market"), _Tool("second", "news")])

    result = await get_user_tool_settings(
        object(),
        SimpleNamespace(id=7, is_admin=True),
    )

    assert set(result.tools) == {"first", "second"}
    assert context_calls == 1
