from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.api import screener as screener_api
from backend.services import settings_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_watchlist_screen_releases_db_before_provider_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_settings(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(watchlist=["AAPL", "MSFT"])

    async def fake_screen(*, universe: list[str], top_n: int):
        assert universe == ["AAPL", "MSFT"]
        assert top_n == 2
        assert db.commits == 1
        return []

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(screener_api, "run_screen", fake_screen)

    result = await screener_api._scan_saved_watchlist(db, current_user=object())

    assert result == {"results": []}
    assert db.commits == 1
