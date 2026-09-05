from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api import correlation as correlation_api


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_correlation_releases_db_before_market_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    portfolio = SimpleNamespace(id=11)
    holdings = [SimpleNamespace(ticker="AAPL"), SimpleNamespace(ticker="MSFT")]

    async def fake_portfolio(received_db, user_id: int):
        assert received_db is db
        assert user_id == 7
        return portfolio

    async def fake_holdings(received_db, portfolio_id: int):
        assert received_db is db
        assert portfolio_id == 11
        return holdings

    async def fake_correlation(tickers: list[str], period: str):
        assert tickers == ["AAPL", "MSFT"]
        assert period == "90d"
        assert db.commits == 1
        return {"tickers": tickers, "matrix": [], "avg_correlation": None, "warning": None}

    monkeypatch.setattr(correlation_api, "get_user_simulation_portfolio", fake_portfolio)
    monkeypatch.setattr(correlation_api, "get_active_holdings", fake_holdings)
    monkeypatch.setattr(correlation_api, "compute_correlation_matrix", fake_correlation)

    result = await correlation_api.get_correlation(
        period="90d",
        db=db,
        current_user=SimpleNamespace(id=7),
    )

    assert result["tickers"] == ["AAPL", "MSFT"]
    assert db.commits == 1
