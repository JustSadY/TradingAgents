from __future__ import annotations

import asyncio
from types import SimpleNamespace

from backend.services.analysis import portfolio_orchestrator as service


class _SessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args) -> bool:
        return False


class _Db:
    def __init__(self) -> None:
        self.added = []
        self.flushes = 0

    def add(self, row) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushes += 1


def test_portfolio_ticker_concurrency_is_provider_aware() -> None:
    assert service._portfolio_ticker_concurrency(
        SimpleNamespace(analyst_concurrency_limit=8, llm_provider="openai")
    ) == 2
    assert service._portfolio_ticker_concurrency(
        SimpleNamespace(analyst_concurrency_limit=8, llm_provider="NVIDIA")
    ) == 1
    assert service._portfolio_ticker_concurrency(
        SimpleNamespace(analyst_concurrency_limit=8, llm_provider="ollama")
    ) == 1
    assert service._portfolio_ticker_concurrency(
        SimpleNamespace(analyst_concurrency_limit=1, llm_provider="openai")
    ) == 1


async def test_portfolio_analysis_bounds_outer_graphs_and_deduplicates_tickers(monkeypatch) -> None:
    active = 0
    max_active = 0
    started: list[str] = []
    release = asyncio.Event()

    async def fake_run(ticker, *_args, **_kwargs):
        nonlocal active, max_active
        started.append(ticker)
        active += 1
        max_active = max(max_active, active)
        if active >= 2:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        active -= 1
        return None, SimpleNamespace(id=len(started), final_decision="Hold")

    monkeypatch.setattr(service, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(service, "run_individual_analysis", fake_run)
    monkeypatch.setattr(service, "_generate_portfolio_overview", lambda **_kwargs: asyncio.sleep(0, result="overview"))

    settings = SimpleNamespace(
        analyst_concurrency_limit=9,
        llm_provider="openai",
        output_language="English",
    )
    db = _Db()

    result = await service.run_portfolio_analysis(
        ["aapl", "AAPL", "msft", "nvda", "googl"],
        "2026-09-04",
        "stock",
        settings,
        db,
    )

    assert max_active == 2
    assert started.count("AAPL") == 1
    assert set(started) == {"AAPL", "MSFT", "NVDA", "GOOGL"}
    assert result.tickers == ["AAPL", "MSFT", "NVDA", "GOOGL"]
    assert db.flushes == 1
