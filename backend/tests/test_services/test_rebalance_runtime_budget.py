from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import portfolio_rebalance_service as service


async def test_healthy_rebalance_plan_skips_context_and_llm(monkeypatch) -> None:
    portfolio = {"holdings": [{"ticker": "AAPL"}], "total_value": 1000.0}
    get_portfolio = AsyncMock(return_value=portfolio)
    fetch_sectors = AsyncMock(side_effect=AssertionError("sector context should not be loaded"))
    get_signals = AsyncMock(side_effect=AssertionError("signal context should not be loaded"))
    call_llm = AsyncMock(side_effect=AssertionError("LLM should not be called"))

    monkeypatch.setattr("backend.services.mock_trading_service.get_portfolio_with_live_prices", get_portfolio)
    monkeypatch.setattr(
        service,
        "build_plan",
        lambda _portfolio: {"score": 100, "cash_pct": 10.0, "issues": [], "suggestions": []},
    )
    monkeypatch.setattr(service, "_fetch_sectors", fetch_sectors)
    monkeypatch.setattr(service, "_get_recent_signals", get_signals)
    monkeypatch.setattr(service, "_call_llm", call_llm)

    result = await service.get_rebalance_suggestions(object(), SimpleNamespace(id=7))

    assert result == {
        "summary": "No concentration or cash-allocation issues found.",
        "score": 100,
        "issues": [],
        "suggestions": [],
    }
    fetch_sectors.assert_not_awaited()
    get_signals.assert_not_awaited()
    call_llm.assert_not_awaited()


async def test_rebalance_market_and_signal_context_start_concurrently(monkeypatch) -> None:
    portfolio = {
        "holdings": [{"ticker": "AAPL", "market_value": 900.0, "pnl_pct": 0.0}],
        "total_value": 1000.0,
    }
    release = asyncio.Event()
    active = 0
    max_active = 0

    async def _wait_for_peer(value):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active >= 2:
            release.set()
        await release.wait()
        active -= 1
        return value

    async def fake_sectors(_tickers):
        return await _wait_for_peer({"AAPL": "Technology"})

    async def fake_signals(_db, _user, _tickers):
        return await _wait_for_peer([])

    monkeypatch.setattr(
        "backend.services.mock_trading_service.get_portfolio_with_live_prices",
        AsyncMock(return_value=portfolio),
    )
    monkeypatch.setattr(
        service,
        "build_plan",
        lambda _portfolio: {
            "score": 70,
            "cash_pct": 10.0,
            "issues": ["Concentration"],
            "suggestions": [
                {
                    "action": "SELL",
                    "ticker": "AAPL",
                    "quantity": 1,
                    "notional": 100.0,
                    "weight_pct": 90.0,
                    "urgency": "medium",
                }
            ],
        },
    )
    monkeypatch.setattr(service, "_fetch_sectors", fake_sectors)
    monkeypatch.setattr(service, "_get_recent_signals", fake_signals)
    monkeypatch.setattr(service, "_call_llm", AsyncMock(return_value={"summary": "ok", "rationales": ["why"]}))

    result = await service.get_rebalance_suggestions(object(), SimpleNamespace(id=7))

    assert max_active == 2
    assert result["summary"] == "ok"
    assert result["suggestions"][0]["rationale"] == "why"


async def test_rebalance_sector_lookups_are_bounded(monkeypatch) -> None:
    active = 0
    max_active = 0
    release = asyncio.Event()

    async def fake_sector(ticker: str) -> str:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active >= service._REBALANCE_SECTOR_CONCURRENCY:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        active -= 1
        return f"sector:{ticker}"

    monkeypatch.setattr(service, "fetch_sector", fake_sector)
    tickers = [f"T{index}" for index in range(12)]

    sectors = await service._fetch_sectors(tickers)

    assert max_active == service._REBALANCE_SECTOR_CONCURRENCY
    assert sectors == {ticker: f"sector:{ticker}" for ticker in tickers}
