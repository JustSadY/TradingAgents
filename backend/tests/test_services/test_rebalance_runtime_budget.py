from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import portfolio_rebalance_service as service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0
        self.commit_event = asyncio.Event()

    async def commit(self) -> None:
        self.commits += 1
        self.commit_event.set()


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
    db = _TrackingDB()

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

    result = await service.get_rebalance_suggestions(db, SimpleNamespace(id=7))

    assert max_active == 2
    assert db.commits == 1
    assert result["summary"] == "ok"
    assert result["suggestions"][0]["rationale"] == "why"


async def test_rebalance_releases_db_while_sector_io_is_still_waiting(monkeypatch) -> None:
    portfolio = {
        "holdings": [{"ticker": "AAPL", "market_value": 900.0, "pnl_pct": 0.0}],
        "total_value": 1000.0,
    }
    db = _TrackingDB()
    sector_started = asyncio.Event()
    allow_sector_finish = asyncio.Event()

    async def fake_sectors(_tickers):
        sector_started.set()
        await allow_sector_finish.wait()
        return {"AAPL": "Technology"}

    async def fake_signals(_db, _user, _tickers):
        await sector_started.wait()
        return []

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

    task = asyncio.create_task(service.get_rebalance_suggestions(db, SimpleNamespace(id=7)))
    await db.commit_event.wait()

    assert db.commits == 1
    assert not task.done()

    allow_sector_finish.set()
    result = await task
    assert result["summary"] == "ok"


async def test_rebalance_llm_releases_settings_transaction_before_provider_call(monkeypatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7)

    async def get_settings(_db, _user):
        return SimpleNamespace(
            llm_provider="ollama",
            llm_model="llama3.2",
            output_language="English",
        )

    async def runtime_context(_db, _user_id):
        return {}

    class CommitAwareLLM:
        async def ainvoke(self, _messages):
            assert db.commits == 1
            return SimpleNamespace(content='{"summary":"ok","rationales":["why"]}')

    class Client:
        def get_llm(self):
            return CommitAwareLLM()

    monkeypatch.setattr("backend.services.settings_service.get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", runtime_context)
    monkeypatch.setattr("backend.services.user_service.get_user_api_key", lambda _user, _provider, _fernet: None)
    monkeypatch.setattr("backend.core.config.get_settings", lambda: SimpleNamespace(get_fernet=lambda: None))
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: False)
    monkeypatch.setattr("backend.trading_agents.llm_clients.factory.create_llm_client", lambda **_kwargs: Client())

    result = await service._call_llm(db, user, "prompt")

    assert result == {"summary": "ok", "rationales": ["why"]}
    assert db.commits == 1


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
