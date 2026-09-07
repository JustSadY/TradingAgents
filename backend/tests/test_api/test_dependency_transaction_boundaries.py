from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api import deps


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_get_current_user_releases_auth_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)

    async def fake_user_from_token(token: str, received_db):
        assert token == "token"
        assert received_db is db
        assert db.commits == 0
        return user

    monkeypatch.setattr(deps, "get_user_from_access_token", fake_user_from_token)

    result = await deps.get_current_user(token="token", db=db)

    assert result is user
    assert db.commits == 1


@pytest.mark.asyncio
async def test_require_page_releases_permission_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)

    async def fake_access(received_db, received_user, page_key: str) -> bool:
        assert received_db is db
        assert received_user is user
        assert page_key == "chart"
        assert db.commits == 0
        return True

    monkeypatch.setattr(deps, "has_page_access", fake_access)
    check = deps.require_page("chart")

    result = await check(current_user=user, db=db)

    assert result is user
    assert db.commits == 1


@pytest.mark.asyncio
async def test_require_any_page_releases_permission_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)

    async def fake_pages(received_db, user_id: int):
        assert received_db is db
        assert user_id == 7
        assert db.commits == 0
        return {"performance"}

    monkeypatch.setattr(deps, "list_allowed_page_keys", fake_pages)
    check = deps.require_any_page("analysis", "performance")

    result = await check(current_user=user, db=db)

    assert result is user
    assert db.commits == 1
