from __future__ import annotations

from types import SimpleNamespace

from backend.schemas.agent_settings import AgentSettingsUpdate
from backend.services.agent_settings_service import apply_agent_settings_update_by_scope


class _Db:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


async def test_agent_settings_update_reuses_loaded_rows_for_response(monkeypatch) -> None:
    repo_calls = 0

    async def fake_get(_db, scope, user_id):
        nonlocal repo_calls
        assert scope == "user"
        assert user_id == 7
        repo_calls += 1
        return []

    def fake_persist(_db, *, agent_key, enabled, settings, **_kwargs):
        return SimpleNamespace(agent_key=agent_key, enabled=enabled, settings=settings)

    monkeypatch.setattr("backend.repositories.agent_settings.get_agent_settings_by_scope", fake_get)
    monkeypatch.setattr("backend.repositories.agent_settings.persist_agent_setting", fake_persist)

    db = _Db()
    result = await apply_agent_settings_update_by_scope(
        db,
        "user",
        AgentSettingsUpdate(agents={"market": {"enabled": False}}),
        user_id=7,
    )

    assert result.agents["market"].enabled is False
    assert repo_calls == 1
    assert db.flushes == 1
