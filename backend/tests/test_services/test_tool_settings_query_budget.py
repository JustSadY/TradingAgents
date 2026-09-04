from __future__ import annotations

from types import SimpleNamespace

from backend.schemas.tool_settings import ToolSettingsUpdate
from backend.services.tool_settings_service import apply_tool_settings_update, get_user_tool_settings, registry


class _Tool:
    def __init__(self, key: str, analyst: str) -> None:
        self.key = key
        self.allowed_analysts = [analyst]
        self.default_enabled = True
        self.settings_schema = []

    def default_settings(self, *, scope: str) -> dict:
        assert scope == "user"
        return {}


class _Db:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


class _Hierarchy:
    def __init__(self, context):
        self.context = context

    def is_enabled(self, agent_key: str) -> bool:
        return bool(self.context.get(agent_key, {}).get("enabled", True))


async def test_user_tool_settings_builds_agent_hierarchy_once_for_all_tools(monkeypatch) -> None:
    context_calls = 0

    async def fake_rows(_db, _user_id):
        return []

    async def fake_context(_db, user_id):
        nonlocal context_calls
        assert user_id == 7
        context_calls += 1
        return {"market": {"enabled": True}, "news": {"enabled": True}}

    monkeypatch.setattr("backend.repositories.tool_settings.get_user_tool_settings", fake_rows)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_context)
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", _Hierarchy)
    monkeypatch.setattr(registry, "list", lambda: [_Tool("first", "market"), _Tool("second", "news")])

    result = await get_user_tool_settings(
        object(),
        SimpleNamespace(id=7, is_admin=True),
    )

    assert set(result.tools) == {"first", "second"}
    assert context_calls == 1


async def test_non_admin_tool_settings_reads_one_unified_access_snapshot(monkeypatch) -> None:
    access_calls = 0

    async def fake_rows(_db, _user_id):
        return []

    async def fake_context(_db, _user_id):
        return {"market": {"enabled": True}, "news": {"enabled": True}}

    async def fake_access(_db, user_id):
        nonlocal access_calls
        assert user_id == 7
        access_calls += 1
        return {"agent_access": {}, "tool_access": {}, "field_access": {}}

    monkeypatch.setattr("backend.repositories.tool_settings.get_user_tool_settings", fake_rows)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_context)
    monkeypatch.setattr("backend.services.tool_settings_service.get_user_access_overrides", fake_access)
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", _Hierarchy)
    monkeypatch.setattr(registry, "list", lambda: [_Tool("first", "market"), _Tool("second", "news")])

    result = await get_user_tool_settings(
        object(),
        SimpleNamespace(id=7, is_admin=False),
    )

    assert set(result.tools) == {"first", "second"}
    assert access_calls == 1


async def test_tool_update_reuses_loaded_rows_and_agent_context_for_response(monkeypatch) -> None:
    row_queries = 0
    context_calls = 0
    tool = _Tool("first", "market")

    async def fake_rows(_db, user_id):
        nonlocal row_queries
        assert user_id == 7
        row_queries += 1
        return []

    async def fake_context(_db, user_id):
        nonlocal context_calls
        assert user_id == 7
        context_calls += 1
        return {"market": {"enabled": True}}

    def fake_ensure(_db, *, tool_key, default_enabled, **_kwargs):
        return SimpleNamespace(tool_key=tool_key, enabled=default_enabled, settings={})

    monkeypatch.setattr("backend.repositories.tool_settings.get_user_tool_settings", fake_rows)
    monkeypatch.setattr("backend.repositories.tool_settings.ensure_tool_setting", fake_ensure)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_context)
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", _Hierarchy)
    monkeypatch.setattr(registry, "list", lambda: [tool])
    monkeypatch.setattr(registry, "get", lambda key: tool if key == tool.key else None)

    db = _Db()
    result = await apply_tool_settings_update(
        db,
        SimpleNamespace(id=7, is_admin=True),
        ToolSettingsUpdate(tools={"first": {"enabled": False}}),
    )

    assert result.tools["first"].enabled is False
    assert row_queries == 1
    assert context_calls == 1
    assert db.flushes == 1
