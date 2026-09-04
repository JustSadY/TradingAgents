import asyncio

from backend.services import market_data_service


async def test_individual_price_fallbacks_are_bounded(monkeypatch) -> None:
    active = 0
    max_active = 0

    async def fake_live_price(symbol: str) -> float:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return float(symbol.removeprefix("T")) + 1.0

    monkeypatch.setattr(market_data_service, "get_live_price", fake_live_price)
    symbols = [f"T{index}" for index in range(20)]

    prices = await market_data_service._fetch_individual_fallbacks(symbols)

    assert len(prices) == 20
    assert prices["T0"] == 1.0
    assert prices["T19"] == 20.0
    assert max_active == market_data_service._INDIVIDUAL_PRICE_CONCURRENCY == 8
