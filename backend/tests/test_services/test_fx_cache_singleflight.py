from __future__ import annotations

import asyncio

from backend.api import fx


async def test_fx_cache_fill_is_singleflight(monkeypatch) -> None:
    fx._cache.clear()
    monkeypatch.setattr(fx, "_cache_fill_lock", asyncio.Lock())

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0
    payload = {"USD": 1.0, "EUR": 1.1}

    async def fake_fetch():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return payload

    monkeypatch.setattr(fx, "_fetch_rates", fake_fetch)

    first = asyncio.create_task(fx._get_cached_rates())
    await started.wait()
    second = asyncio.create_task(fx._get_cached_rates())
    await asyncio.sleep(0)
    release.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert calls == 1
    assert first_result == payload
    assert second_result == payload
