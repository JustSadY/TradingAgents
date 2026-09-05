from __future__ import annotations

import pandas as pd

from backend.services.analysis import market_pulse_service


async def test_current_regime_snapshot_uses_broad_market_inputs(monkeypatch):
    async def fake_prices(_tickers):
        return {"^VIX": 32.0}

    async def fake_history(_ticker, _start, _end):
        closes = [100.0 + index for index in range(25)]
        return pd.DataFrame({"Close": closes})

    monkeypatch.setattr(market_pulse_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(market_pulse_service, "get_historical_data", fake_history)

    snapshot = await market_pulse_service.get_current_regime_snapshot()

    assert snapshot["trend"] == "bull"
    assert snapshot["volatility"] == "high"
    assert snapshot["risk"] == "risk_off"
    assert snapshot["source"] == "broad_market_v1"
    assert snapshot["as_of"]


async def test_current_regime_snapshot_fetches_live_and_history_together(monkeypatch):
    gather_widths: list[int] = []
    real_gather = market_pulse_service.asyncio.gather

    async def tracked_gather(*awaitables):
        gather_widths.append(len(awaitables))
        return await real_gather(*awaitables)

    async def fake_prices(_tickers):
        return {"^VIX": 18.0}

    async def fake_history(_ticker, _start, _end):
        return pd.DataFrame({"Close": [100.0] * 25})

    monkeypatch.setattr(market_pulse_service.asyncio, "gather", tracked_gather)
    monkeypatch.setattr(market_pulse_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(market_pulse_service, "get_historical_data", fake_history)

    snapshot = await market_pulse_service.get_current_regime_snapshot()

    assert gather_widths == [2]
    assert snapshot["trend"] == "range_bound"
    assert snapshot["volatility"] == "normal"


async def test_current_regime_snapshot_fails_empty_when_all_sources_are_unavailable(monkeypatch):
    async def fake_prices(_tickers):
        return {}

    async def fake_history(_ticker, _start, _end):
        return pd.DataFrame()

    monkeypatch.setattr(market_pulse_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(market_pulse_service, "get_historical_data", fake_history)

    assert await market_pulse_service.get_current_regime_snapshot() == {}