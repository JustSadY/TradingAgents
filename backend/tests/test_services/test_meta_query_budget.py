from __future__ import annotations

from types import SimpleNamespace

import backend.core.catalog as catalog
from backend.core.catalog import build_meta


async def test_non_admin_meta_reuses_one_access_snapshot_for_tools_and_analysts(monkeypatch) -> None:
    access_calls = 0

    async def fake_agent_context(_db, user_id):
        assert user_id == 7
        return {"market": {"enabled": True}, "news": {"enabled": True}}

    async def fake_access(_db, user_id):
        nonlocal access_calls
        assert user_id == 7
        access_calls += 1
        return {
            "agent_access": {"market": False},
            "tool_access": {},
            "field_access": {},
        }

    async def fake_personas(_db, _user):
        return []

    class FakeHierarchy:
        def __init__(self, context):
            self.context = context

        def is_enabled(self, agent_key: str) -> bool:
            return bool(self.context.get(agent_key, {}).get("enabled", True))

    analysts = [
        SimpleNamespace(key="market", label="Market", description="market", default_on=True),
        SimpleNamespace(key="news", label="News", description="news", default_on=True),
    ]

    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", fake_agent_context)
    monkeypatch.setattr("backend.services.tool_access_service.get_user_access_overrides", fake_access)
    monkeypatch.setattr("backend.trading_agents.agent_catalog.list_agents", lambda: [])
    monkeypatch.setattr("backend.trading_agents.agents.hierarchy.AgentHierarchy", FakeHierarchy)
    monkeypatch.setattr("backend.trading_agents.agents.tools.registry.metadata", lambda: [])
    monkeypatch.setattr(catalog, "_engine_analysts", lambda: analysts)
    monkeypatch.setattr(catalog, "_node_specs", lambda: {})
    monkeypatch.setattr(catalog, "investor_personas", fake_personas)

    meta = await build_meta(object(), SimpleNamespace(id=7, is_admin=False, is_owner=False))

    assert access_calls == 1
    assert [analyst["key"] for analyst in meta["analysts"]] == ["news"]
