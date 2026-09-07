from __future__ import annotations

from types import SimpleNamespace

import backend.services.tool_access_service as access_service
from backend.services.tool_access_service import (
    update_user_agent_access,
    update_user_tool_access,
    update_user_tool_field_access,
)


class _Db:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


def _tool() -> SimpleNamespace:
    return SimpleNamespace(
        key="search_web",
        settings_schema=[SimpleNamespace(key="searxng_url")],
    )


async def test_agent_access_update_preloads_once_and_skips_default_override(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0

    async def fake_rows(_db, user_id):
        nonlocal preload_calls
        assert user_id == 7
        preload_calls += 1
        return []

    def fake_ensure(*_args, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        raise AssertionError("default permission must not create an override")

    monkeypatch.setattr(access_service, "list_analysts", lambda: ["market"])
    monkeypatch.setattr(access_service, "list_agent_access_rows", fake_rows)
    monkeypatch.setattr(access_service, "ensure_agent_access_row", fake_ensure)

    db = _Db()
    result = await update_user_agent_access(db, 7, {"market": True})

    assert result == {"market": True}
    assert preload_calls == 1
    assert ensure_calls == 0
    assert db.flushes == 0


async def test_agent_access_real_change_uses_loaded_snapshot_without_requery(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0

    async def fake_rows(_db, _user_id):
        nonlocal preload_calls
        preload_calls += 1
        return []

    def fake_ensure(_db, *, user_id, agent_key, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        return SimpleNamespace(user_id=user_id, agent_key=agent_key, can_run=True)

    monkeypatch.setattr(access_service, "list_analysts", lambda: ["market"])
    monkeypatch.setattr(access_service, "list_agent_access_rows", fake_rows)
    monkeypatch.setattr(access_service, "ensure_agent_access_row", fake_ensure)

    db = _Db()
    result = await update_user_agent_access(db, 7, {"market": False})

    assert result == {"market": False}
    assert preload_calls == 1
    assert ensure_calls == 1
    assert db.flushes == 1


async def test_tool_access_update_is_sparse_and_single_preload(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0
    tool = _tool()

    async def fake_rows(_db, _user_id):
        nonlocal preload_calls
        preload_calls += 1
        return []

    def fake_ensure(_db, *, user_id, tool_key, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        return SimpleNamespace(
            user_id=user_id,
            tool_key=tool_key,
            can_view=True,
            can_use=True,
            can_edit=False,
            can_enable=False,
        )

    monkeypatch.setattr(access_service.registry, "list", lambda: [tool])
    monkeypatch.setattr(access_service.registry, "get", lambda key: tool if key == tool.key else None)
    monkeypatch.setattr(access_service, "list_tool_access_rows", fake_rows)
    monkeypatch.setattr(access_service, "ensure_tool_access_row", fake_ensure)

    no_op_db = _Db()
    no_op = await update_user_tool_access(no_op_db, 7, {"search_web": {"can_view": True}})
    assert no_op["search_web"]["can_view"] is True
    assert ensure_calls == 0
    assert no_op_db.flushes == 0

    changed_db = _Db()
    changed = await update_user_tool_access(changed_db, 7, {"search_web": {"can_use": False}})
    assert changed["search_web"]["can_use"] is False
    assert preload_calls == 2
    assert ensure_calls == 1
    assert changed_db.flushes == 1


async def test_field_access_update_is_sparse_and_single_preload(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0
    tool = _tool()

    async def fake_rows(_db, _user_id):
        nonlocal preload_calls
        preload_calls += 1
        return []

    def fake_ensure(_db, *, user_id, tool_key, field_key, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        return SimpleNamespace(
            user_id=user_id,
            tool_key=tool_key,
            field_key=field_key,
            can_view=True,
            can_edit=True,
        )

    monkeypatch.setattr(access_service.registry, "list", lambda: [tool])
    monkeypatch.setattr(access_service.registry, "get", lambda key: tool if key == tool.key else None)
    monkeypatch.setattr(access_service, "list_tool_field_access_rows", fake_rows)
    monkeypatch.setattr(access_service, "ensure_tool_field_access_row", fake_ensure)

    no_op_db = _Db()
    no_op = await update_user_tool_field_access(
        no_op_db,
        7,
        {"search_web": {"searxng_url": {"can_view": True, "can_edit": True}}},
    )
    assert no_op["search_web"]["searxng_url"] == {"can_view": True, "can_edit": True}
    assert ensure_calls == 0
    assert no_op_db.flushes == 0

    changed_db = _Db()
    changed = await update_user_tool_field_access(
        changed_db,
        7,
        {"search_web": {"searxng_url": {"can_view": False}}},
    )
    assert changed["search_web"]["searxng_url"]["can_view"] is False
    assert preload_calls == 2
    assert ensure_calls == 1
    assert changed_db.flushes == 1
