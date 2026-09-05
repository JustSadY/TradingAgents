from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.api import watchlist as watchlist_api


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_watchlist_prices_release_db_before_market_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_settings(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(watchlist=["AAPL", "MSFT"])

    async def fake_prices(tickers: list[str]) -> dict[str, dict[str, float]]:
        assert tickers == ["AAPL", "MSFT"]
        assert db.commits == 1
        return {"AAPL": {"price": 100.0}, "MSFT": {"price": 200.0}}

    monkeypatch.setattr(watchlist_api, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(watchlist_api, "get_live_prices_details_batch", fake_prices)

    result = await watchlist_api.get_watchlist_prices(db=db, current_user=object())

    assert result["AAPL"]["price"] == 100.0
    assert db.commits == 1
