from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import deps


@pytest.mark.asyncio
async def test_require_any_page_uses_one_allowed_page_snapshot(monkeypatch) -> None:
    calls = 0

    async def fake_allowed(_db, user_id):
        nonlocal calls
        assert user_id == 7
        calls += 1
        return {"chart"}

    monkeypatch.setattr(deps, "list_allowed_page_keys", fake_allowed)
    checker = deps.require_any_page("analysis", "chart", "performance", "dashboard")
    user = SimpleNamespace(id=7, is_admin=False)

    result = await checker(current_user=user, db=object())

    assert result is user
    assert calls == 1


@pytest.mark.asyncio
async def test_require_any_page_denies_after_one_snapshot(monkeypatch) -> None:
    calls = 0

    async def fake_allowed(_db, _user_id):
        nonlocal calls
        calls += 1
        return {"watchlist"}

    monkeypatch.setattr(deps, "list_allowed_page_keys", fake_allowed)
    checker = deps.require_any_page("analysis", "chart", "performance", "dashboard")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=SimpleNamespace(id=7, is_admin=False), db=object())

    assert exc.value.status_code == 403
    assert calls == 1
