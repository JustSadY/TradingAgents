from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace

from backend.services import alert_service


async def test_indicator_history_fetches_are_deduplicated_and_bounded(monkeypatch) -> None:
    calls: Counter[str] = Counter()
    active = 0
    max_active = 0
    release = asyncio.Event()

    async def fake_fetch(ticker: str, period: str = "6mo"):
        nonlocal active, max_active
        assert period == "6mo"
        calls[ticker] += 1
        active += 1
        max_active = max(max_active, active)
        if active >= 5:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        active -= 1
        return ticker

    tickers = [f"T{index}" for index in range(12)]
    alerts = [SimpleNamespace(ticker=ticker) for ticker in tickers]
    alerts += [SimpleNamespace(ticker=ticker) for ticker in tickers[:3]]

    monkeypatch.setattr(alert_service, "_ALERT_SEMAPHORE", asyncio.Semaphore(5))
    monkeypatch.setattr(alert_service, "_fetch_close_series", fake_fetch)

    histories = await alert_service._fetch_indicator_histories(alerts)

    assert histories == {ticker: ticker for ticker in tickers}
    assert calls == Counter({ticker: 1 for ticker in tickers})
    assert max_active == 5
