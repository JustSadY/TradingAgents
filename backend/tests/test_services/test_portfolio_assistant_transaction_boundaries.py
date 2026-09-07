from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from backend.repositories import portfolio as portfolio_repo
from backend.services import market_data_service, portfolio_assistant_service, settings_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _FakeTool:
    async def ainvoke(self, _args: dict) -> str:
        return "tool result"


class _TwoRoundLLM:
    def __init__(self, db: _TrackingDB) -> None:
        self.db = db
        self.calls = 0

    async def ainvoke(self, _messages: list):
        self.calls += 1
        if self.calls == 1:
            assert self.db.commits == 1
            return AIMessage(
                content="",
                tool_calls=[{"name": "read_tool", "args": {}, "id": "call-1", "type": "tool_call"}],
            )
        assert self.db.commits == 2
        return AIMessage(content="done")


@pytest.mark.asyncio
async def test_assistant_releases_db_before_every_llm_round() -> None:
    db = _TrackingDB()
    llm = _TwoRoundLLM(db)

    result = await portfolio_assistant_service._run_tool_loop(
        db,
        llm,
        [],
        {"read_tool": _FakeTool()},
    )

    assert result == "done"
    assert db.commits == 2


@pytest.mark.asyncio
async def test_assistant_watchlist_releases_db_before_market_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)

    async def fake_settings(*_args: Any, **_kwargs: Any):
        return SimpleNamespace(watchlist=["AAPL", "MSFT"])

    async def fake_prices(tickers: list[str]):
        assert tickers == ["AAPL", "MSFT"]
        assert db.commits == 1
        return {"AAPL": 100.0, "MSFT": 200.0}

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(market_data_service, "get_live_prices_batch", fake_prices)

    result = await portfolio_assistant_service._tool_get_watchlist(db, user, {"watchlist"})

    assert "AAPL: $100.00" in result
    assert db.commits == 1


@pytest.mark.asyncio
async def test_assistant_portfolio_summary_releases_db_before_market_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)
    holding = SimpleNamespace(
        ticker="AAPL",
        quantity=2.0,
        avg_buy_price=50.0,
        unrealized_pnl=10.0,
    )
    portfolio = SimpleNamespace(
        cash_available=900.0,
        current_balance=1010.0,
        holdings=[holding],
    )

    async def fake_portfolio(*_args: Any, **_kwargs: Any):
        return portfolio

    async def fake_prices(tickers: list[str]):
        assert tickers == ["AAPL"]
        assert db.commits == 1
        return {"AAPL": 60.0}

    monkeypatch.setattr(portfolio_repo, "get_simulation_portfolio", fake_portfolio)
    monkeypatch.setattr(market_data_service, "get_live_prices_batch", fake_prices)

    result = await portfolio_assistant_service._tool_get_portfolio_summary(db, user, {"portfolio"})

    assert "current $60.00" in result
    assert db.commits == 1
