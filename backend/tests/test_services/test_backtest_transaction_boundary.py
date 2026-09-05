from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services import backtest_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _price_frame() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=30, freq="B")
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0 + i for i in range(len(dates))],
            "High": [101.0 + i for i in range(len(dates))],
            "Low": [99.0 + i for i in range(len(dates))],
            "Close": [100.5 + i for i in range(len(dates))],
        }
    )


@pytest.mark.asyncio
async def test_consensus_backtest_releases_db_after_analysis_load(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    def fake_prices(_ticker: str, _end_date: str):
        return _price_frame()

    async def fake_consensus(received_db, ticker: str, start_date: str, end_date: str, user):
        assert received_db is db
        assert ticker == "AAPL"
        assert user.id == 7
        assert db.commits == 0
        return {}, {"considered": 0, "used": 0}

    async def fake_benchmark(*_args, **_kwargs):
        assert db.commits == 1
        return None

    monkeypatch.setattr(backtest_service, "load_ohlcv", fake_prices)
    monkeypatch.setattr(backtest_service, "_load_consensus_analyses", fake_consensus)
    monkeypatch.setattr(backtest_service, "_benchmark_return", fake_benchmark)

    result = await backtest_service.run_backtest_simulation(
        db,
        ticker="AAPL",
        strategy_type="consensus",
        start_date="2025-01-01",
        end_date="2025-02-11",
        user=SimpleNamespace(id=7),
    )

    assert "error" not in result
    assert db.commits == 1


@pytest.mark.asyncio
async def test_rule_backtest_does_not_commit_service_caller_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    def fake_prices(_ticker: str, _end_date: str):
        return _price_frame()

    async def fake_benchmark(*_args, **_kwargs):
        assert db.commits == 0
        return None

    monkeypatch.setattr(backtest_service, "load_ohlcv", fake_prices)
    monkeypatch.setattr(backtest_service, "_benchmark_return", fake_benchmark)

    result = await backtest_service.run_backtest_simulation(
        db,
        ticker="AAPL",
        strategy_type="rsi_oversold",
        start_date="2025-01-01",
        end_date="2025-02-11",
    )

    assert "error" not in result
    assert db.commits == 0
