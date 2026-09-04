from __future__ import annotations

import asyncio

from backend.services import market_data_service, sector_rotation_service


async def test_individual_price_fallback_reuses_one_http_client(monkeypatch) -> None:
    created_clients: list[object] = []
    seen_clients: list[object] = []

    class _ClientContext:
        async def __aenter__(self):
            client = object()
            created_clients.append(client)
            return client

        async def __aexit__(self, *_args) -> bool:
            return False

    async def fake_direct(symbol: str, client) -> float:
        seen_clients.append(client)
        return {"AAPL": 101.0, "MSFT": 202.0, "NVDA": 303.0}[symbol]

    async def history_should_not_run(_symbol: str):
        raise AssertionError("history fallback should not run after a direct quote")

    monkeypatch.setattr(market_data_service.httpx, "AsyncClient", _ClientContext)
    monkeypatch.setattr(market_data_service, "_fetch_direct_live_price", fake_direct)
    monkeypatch.setattr(market_data_service, "_fetch_history_price_fallback", history_should_not_run)

    result = await market_data_service._fetch_individual_fallbacks(["AAPL", "MSFT", "NVDA"])

    assert result == {"AAPL": 101.0, "MSFT": 202.0, "NVDA": 303.0}
    assert len(created_clients) == 1
    assert seen_clients == [created_clients[0], created_clients[0], created_clients[0]]


async def test_sector_rotation_cache_fill_is_singleflight(monkeypatch) -> None:
    sector_rotation_service._cache.clear()
    monkeypatch.setattr(sector_rotation_service, "_cache_fill_lock", asyncio.Lock())

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    payload = [{"ticker": "XLK", "momentum_score": 0.5}]

    async def fake_load():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return payload

    monkeypatch.setattr(sector_rotation_service, "_load_sector_rotation", fake_load)

    first = asyncio.create_task(sector_rotation_service.get_sector_rotation())
    await started.wait()
    second = asyncio.create_task(sector_rotation_service.get_sector_rotation())
    await asyncio.sleep(0)
    release.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert calls == 1
    assert first_result == payload
    assert second_result == payload
