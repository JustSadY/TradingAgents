from __future__ import annotations

from types import SimpleNamespace

import backend.services.user_service as user_service
from backend.core.constants import SETTING_KEYS
from backend.models.page_permission import ALL_PAGE_KEYS
from backend.services.user_service import set_managed_page_permissions, set_managed_setting_permissions


class _Db:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


async def test_page_permissions_preload_once_and_skip_default_false(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0
    page_key = ALL_PAGE_KEYS[0]

    async def fake_user(_db, user_id):
        return SimpleNamespace(id=user_id)

    async def fake_rows(_db, user_id):
        nonlocal preload_calls
        assert user_id == 7
        preload_calls += 1
        return []

    def fake_ensure(*_args, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        raise AssertionError("default false permission must remain sparse")

    monkeypatch.setattr(user_service, "get_user_or_raise", fake_user)
    monkeypatch.setattr("backend.repositories.permissions.list_user_page_permission_rows", fake_rows)
    monkeypatch.setattr("backend.repositories.permissions.ensure_user_page_permission_row", fake_ensure)

    db = _Db()
    await set_managed_page_permissions(db, 7, {page_key: False})

    assert preload_calls == 1
    assert ensure_calls == 0
    assert db.flushes == 0


async def test_page_permission_real_change_uses_loaded_snapshot(monkeypatch) -> None:
    preload_calls = 0
    page_key = ALL_PAGE_KEYS[0]

    async def fake_user(_db, user_id):
        return SimpleNamespace(id=user_id)

    async def fake_rows(_db, _user_id):
        nonlocal preload_calls
        preload_calls += 1
        return []

    def fake_ensure(_db, *, user_id, page_key, **_kwargs):
        return SimpleNamespace(user_id=user_id, page_key=page_key, allowed=False)

    monkeypatch.setattr(user_service, "get_user_or_raise", fake_user)
    monkeypatch.setattr("backend.repositories.permissions.list_user_page_permission_rows", fake_rows)
    monkeypatch.setattr("backend.repositories.permissions.ensure_user_page_permission_row", fake_ensure)

    db = _Db()
    await set_managed_page_permissions(db, 7, {page_key: True})

    assert preload_calls == 1
    assert db.flushes == 1


async def test_setting_permissions_preload_once_and_skip_default_false(monkeypatch) -> None:
    preload_calls = 0
    ensure_calls = 0
    setting_key = SETTING_KEYS[0]

    async def fake_user(_db, user_id):
        return SimpleNamespace(id=user_id)

    async def fake_rows(_db, user_id):
        nonlocal preload_calls
        assert user_id == 7
        preload_calls += 1
        return []

    def fake_ensure(*_args, **_kwargs):
        nonlocal ensure_calls
        ensure_calls += 1
        raise AssertionError("default false setting permission must remain sparse")

    monkeypatch.setattr(user_service, "get_user_or_raise", fake_user)
    monkeypatch.setattr("backend.repositories.permissions.list_user_setting_permission_rows", fake_rows)
    monkeypatch.setattr("backend.repositories.permissions.ensure_user_setting_permission_row", fake_ensure)

    db = _Db()
    await set_managed_setting_permissions(db, 7, {setting_key: False})

    assert preload_calls == 1
    assert ensure_calls == 0
    assert db.flushes == 0


async def test_setting_permission_real_change_uses_loaded_snapshot(monkeypatch) -> None:
    preload_calls = 0
    setting_key = SETTING_KEYS[0]

    async def fake_user(_db, user_id):
        return SimpleNamespace(id=user_id)

    async def fake_rows(_db, _user_id):
        nonlocal preload_calls
        preload_calls += 1
        return []

    def fake_ensure(_db, *, user_id, setting_key, **_kwargs):
        return SimpleNamespace(user_id=user_id, setting_key=setting_key, allowed=False)

    monkeypatch.setattr(user_service, "get_user_or_raise", fake_user)
    monkeypatch.setattr("backend.repositories.permissions.list_user_setting_permission_rows", fake_rows)
    monkeypatch.setattr("backend.repositories.permissions.ensure_user_setting_permission_row", fake_ensure)

    db = _Db()
    await set_managed_setting_permissions(db, 7, {setting_key: True})

    assert preload_calls == 1
    assert db.flushes == 1
