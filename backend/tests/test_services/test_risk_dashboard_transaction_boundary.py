from __future__ import annotations

from typing import Any

import pytest

from backend.services import mock_trading_service, risk_dashboard_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_risk_dashboard_releases_read_transaction_before_market_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_portfolio_snapshot(*_args: Any, **_kwargs: Any) -> dict:
        return {
            "holdings": [
                {
                    "ticker": "AAPL",
                    "market_value": 100.0,
                }
            ]
        }

    async def fake_market_data(tickers: list[str]):
        assert tickers == ["AAPL"]
        assert db.commits == 1
        raise RuntimeError("boundary reached")

    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", fake_portfolio_snapshot)
    monkeypatch.setattr(risk_dashboard_service, "_fetch_market_data", fake_market_data)

    with pytest.raises(RuntimeError, match="boundary reached"):
        await risk_dashboard_service.get_risk_dashboard(db, user=object())

    assert db.commits == 1
