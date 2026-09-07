from __future__ import annotations

import asyncio

from backend.services import risk_dashboard_service as service


async def test_risk_market_data_fanout_is_bounded(monkeypatch) -> None:
    active = 0
    max_active = 0
    release = asyncio.Event()

    async def wait_for_slot(value):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active >= service._RISK_FETCH_CONCURRENCY:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        active -= 1
        return value

    async def fake_history(ticker: str, period: str = "3mo"):
        assert period == "3mo"
        return await wait_for_slot(None)

    async def fake_sector(ticker: str):
        return await wait_for_slot(f"sector:{ticker}")

    monkeypatch.setattr(service, "_fetch_close_history", fake_history)
    monkeypatch.setattr(service, "fetch_sector", fake_sector)

    tickers = [f"T{index}" for index in range(10)]
    ticker_hist, spy_returns, sector_map = await service._fetch_market_data(tickers)

    assert max_active == service._RISK_FETCH_CONCURRENCY
    assert set(ticker_hist) == set(tickers)
    assert spy_returns is None
    assert sector_map == {ticker: f"sector:{ticker}" for ticker in tickers}
