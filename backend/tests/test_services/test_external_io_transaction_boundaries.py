"""Ensure slow external calls do not pin request database transactions."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services import daily_summary_service, report_chat_service, trade_journal_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0
        self.added: list[object] = []
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushes += 1


class _Client:
    def __init__(self, llm) -> None:
        self._llm = llm

    def get_llm(self):
        return self._llm


@pytest.mark.asyncio
async def test_report_chat_releases_read_transaction_before_llm(monkeypatch):
    db = _TrackingDB()
    user = SimpleNamespace(id=7, is_admin=False)
    analysis = SimpleNamespace(
        id=12,
        ticker="AAPL",
        signal="Buy",
        final_decision="Buy with controlled sizing",
        market_report="Market context",
    )

    async def owned_analysis(_db, _analysis_id, _user):
        return analysis

    async def settings(_db, _user):
        return SimpleNamespace(output_language="English", llm_provider="ollama", llm_model="llama3.2")

    async def prompt_history(_db, _analysis_id):
        return []

    async def runtime_context(_db, _user_id):
        return {}

    class CommitAwareLLM:
        async def ainvoke(self, _messages):
            assert db.commits == 1
            return SimpleNamespace(content="Grounded answer")

    monkeypatch.setattr(report_chat_service, "_get_owned_analysis", owned_analysis)
    monkeypatch.setattr(report_chat_service, "get_or_create_settings", settings)
    monkeypatch.setattr(report_chat_service, "_list_prompt_history", prompt_history)
    monkeypatch.setattr(report_chat_service, "resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", runtime_context)
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: False)
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _Client(CommitAwareLLM()),
    )

    result = await report_chat_service.answer_report_question(db, 12, "What is the thesis?", user)

    assert result.content == "Grounded answer"
    assert db.commits == 1
    assert db.flushes == 1
    assert [getattr(item, "role", None) for item in db.added] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_daily_summary_releases_read_transaction_before_market_and_llm_io(monkeypatch):
    db = _TrackingDB()
    user = SimpleNamespace(id=7)

    async def settings(_db, _user):
        return SimpleNamespace(watchlist=["AAPL"], llm_provider="ollama", llm_model="llama3.2")

    async def runtime_context(_db, _user_id):
        return {}

    async def prices(_watchlist):
        assert db.commits == 1
        return ["  AAPL: $100.00 (+1.0%)"]

    async def sectors():
        assert db.commits == 1
        return ["  Leaders: Technology (+1.0% 1W)"]

    class CommitAwareLLM:
        async def ainvoke(self, _messages):
            assert db.commits == 1
            return SimpleNamespace(content="Market brief")

    monkeypatch.setattr(daily_summary_service, "get_or_create_settings", settings)
    monkeypatch.setattr(daily_summary_service, "resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr(daily_summary_service, "_fetch_watchlist_prices", prices)
    monkeypatch.setattr(daily_summary_service, "_fetch_sector_data", sectors)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", runtime_context)
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: False)
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _Client(CommitAwareLLM()),
    )

    result = await daily_summary_service.generate_daily_summary(db, user)

    assert result["summary"] == "Market brief"
    assert db.commits == 2
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_trade_debrief_releases_read_transaction_before_llm(monkeypatch):
    db = _TrackingDB()
    user = SimpleNamespace(id=7)
    order = SimpleNamespace(
        ticker="AAPL",
        action="sell",
        side="long",
        quantity_filled=Decimal("2"),
        price_per_share=Decimal("110"),
        total_value=Decimal("220"),
        realized_pnl=Decimal("20"),
        commission=Decimal("1"),
        entry_commission=Decimal("1"),
        ai_signal="Buy",
        ai_reasoning="Momentum remained positive.",
    )
    persisted: dict[str, object] = {}

    async def get_order(_db, _order_id, *, user):
        return order

    async def get_note(_db, *, order_id, user_id):
        return SimpleNamespace(note="Followed the plan")

    async def settings(_db, _user):
        return SimpleNamespace(llm_provider="ollama", llm_model="llama3.2")

    async def runtime_context(_db, _user_id):
        return {}

    async def set_debrief(_db, *, order_id, user_id, debrief):
        assert db.commits == 1
        persisted.update(order_id=order_id, user_id=user_id, debrief=debrief)

    class CommitAwareLLM:
        async def ainvoke(self, _messages):
            assert db.commits == 1
            return SimpleNamespace(content="4/5. Execution was disciplined.")

    monkeypatch.setattr(trade_journal_service.portfolio_repo, "get_order_by_id", get_order)
    monkeypatch.setattr(trade_journal_service.repo, "get_note", get_note)
    monkeypatch.setattr(trade_journal_service.repo, "set_debrief", set_debrief)
    monkeypatch.setattr("backend.services.settings_service.get_or_create_settings", settings)
    monkeypatch.setattr("backend.services.agent_settings_service.build_agent_runtime_context", runtime_context)
    monkeypatch.setattr("backend.services.user_service.get_user_api_key", lambda _user, _provider, _fernet: None)
    monkeypatch.setattr("backend.core.config.get_settings", lambda: SimpleNamespace(get_fernet=lambda: None))
    monkeypatch.setattr("backend.trading_agents.llm_clients.registry.provider_requires_api_key", lambda _provider: False)
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _Client(CommitAwareLLM()),
    )

    result = await trade_journal_service.generate_debrief(db, user, 42)

    assert result == {"order_id": 42, "ai_debrief": "4/5. Execution was disciplined."}
    assert db.commits == 2
    assert persisted == {
        "order_id": 42,
        "user_id": 7,
        "debrief": "4/5. Execution was disciplined.",
    }
