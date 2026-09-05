from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api import trading as trading_api


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_backtest_releases_request_db_before_historical_price_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    req = trading_api.BacktestRequest(
        ticker="AAPL",
        strategy_type="rsi_oversold",
        start_date="2025-01-01",
        end_date="2025-03-31",
        benchmark_ticker="SPY",
    )

    async def fake_backtest(_db, **kwargs):
        assert _db is db
        assert db.commits == 1
        assert kwargs["ticker"] == "AAPL"
        return {"total_return": 0.0}

    monkeypatch.setattr(trading_api, "run_backtest_simulation", fake_backtest)

    result = await trading_api.run_backtest(
        req=req,
        db=db,
        _=SimpleNamespace(id=7),
    )

    assert result == {"total_return": 0.0}
    assert db.commits == 1
