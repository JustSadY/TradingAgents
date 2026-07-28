"""Technical-indicator aggregation and local calculation regressions."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.mark.asyncio
async def test_collect_indicators_sends_one_identifier_per_vendor_call(monkeypatch):
    from backend.trading_agents.agents.data import technical_indicators_tools

    calls: list[tuple[str, str, str, int]] = []

    async def fake_route(method: str, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        assert method == "get_indicators"
        calls.append((symbol, indicator, curr_date, look_back_days))
        return f"{indicator}-result"

    monkeypatch.setattr(technical_indicators_tools, "route_to_vendor", fake_route)

    result = await technical_indicators_tools.collect_indicators(
        "AAPL",
        "macd, rsi , atr",
        "2024-05-31",
        45,
    )

    assert calls == [
        ("AAPL", "macd", "2024-05-31", 45),
        ("AAPL", "rsi", "2024-05-31", 45),
        ("AAPL", "atr", "2024-05-31", 45),
    ]
    assert result == "macd-result\n\nrsi-result\n\natr-result"


def test_yfinance_indicator_backend_covers_market_prefetch_indicators(monkeypatch):
    import backend.trading_agents.dataflows.y_finance as y_finance

    dates = pd.date_range("2024-01-02", periods=100, freq="B")
    close = pd.Series(range(100, 200), dtype=float)
    data = pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 1,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": 1000.0,
        }
    )
    monkeypatch.setattr(y_finance, "load_ohlcv", lambda *_args: data.copy())

    for indicator in ("macds", "macdh", "atr", "vwma"):
        result = y_finance.get_stock_stats_indicators_window("AAPL", indicator, "2024-05-31", 30)
        assert result.startswith(f"## {indicator} values for AAPL")
        assert "not yet supported" not in result
