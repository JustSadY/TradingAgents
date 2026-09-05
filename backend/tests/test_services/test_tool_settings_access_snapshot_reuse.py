from types import SimpleNamespace

from backend.schemas.tool_settings import ToolSettingsUpdate
from backend.services.tool_settings_service import apply_tool_settings_update, registry


class _Tool:
    key = "first"
    allowed_analysts = ["market"]
    default_enabled = True
    settings_schema = []

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


async def test_tool_update_reuses_permission_snapshot_for_response(monkeypatch) -> None:
    tool = _Tool()

    async def fake_rows(_db, user_id):
        assert user_id == 7
        return []

    async def fake_context(_db, user_id):
        assert user_id == 7
        return {"market": {"enabled": True}}

    async def access_must_not_reload(*_args, **_kwargs):
        raise AssertionError("request-local access snapshot must be reused")

    def fake_ensure(_db, *, tool_key, default_enabled, **_kwargs):
        return SimpleNamespace(tool_key=tool_key, enabled=default_enabled, settings={})

    monkeypatch.setattr("backend.repositories.tool_settings.get_user_tool_settings", fake_rows)
    monkeypatch.setattr("backend.repositories.tool_settings.ensure_tool_setting", fake_ensure)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_context)
    monkeypatch.setattr("backend.services.tool_settings_service.get_user_access_overrides", access_must_not_reload)
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", _Hierarchy)
    monkeypatch.setattr(registry, "list", lambda: [tool])
    monkeypatch.setattr(registry, "get", lambda key: tool if key == tool.key else None)

    access = {
        "agent_access": {},
        "tool_access": {"first": {"can_view": True, "can_edit": True, "can_enable": True}},
        "field_access": {},
    }
    db = _Db()

    result = await apply_tool_settings_update(
        db,
        SimpleNamespace(id=7, is_admin=False),
        ToolSettingsUpdate(tools={"first": {"enabled": False}}),
        access_snapshot=access,
    )

    assert result.tools["first"].enabled is False
    assert db.flushes == 1
