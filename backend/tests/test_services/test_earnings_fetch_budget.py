from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.services import earnings_service


async def test_earnings_fetch_concurrency_is_bounded(monkeypatch) -> None:
    real_sleep = asyncio.sleep
    release = asyncio.Event()
    active = 0
    max_active = 0

    async def fake_to_thread(_func, ticker: str):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active >= earnings_service._EARNINGS_FETCH_CONCURRENCY:
            release.set()
        await release.wait()
        await real_sleep(0)
        active -= 1
        return earnings_service.EarningsEntry(
            ticker=ticker,
            earnings_date=None,
            eps_estimate=None,
            reported_eps=None,
            surprise_pct=None,
            days_until=None,
            status="unknown",
        )

    monkeypatch.setattr(earnings_service.asyncio, "to_thread", fake_to_thread)

    tickers = [f"T{index}" for index in range(12)]
    results = await earnings_service.get_earnings_calendar(
        object(),
        SimpleNamespace(id=7),
        ",".join(tickers),
    )

    assert len(results) == len(tickers)
    assert max_active == earnings_service._EARNINGS_FETCH_CONCURRENCY
