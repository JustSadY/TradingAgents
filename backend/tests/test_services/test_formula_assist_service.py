"""Credential, resilience, and transaction-boundary coverage for formula assist."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.exceptions import ExternalServiceError
from backend.services import formula_assist_service


class _FormulaDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _FormulaLLM:
    async def ainvoke(self, _messages):
        return SimpleNamespace(content="SMA(20)")


class _FormulaClient:
    def __init__(self, llm=None):
        self._llm = llm or _FormulaLLM()

    def get_llm(self):
        return self._llm


class _SequenceFormulaLLM:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def ainvoke(self, _messages):
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_formula_assist_allows_server_managed_ollama_without_tenant_key(monkeypatch):
    captured: dict[str, str | None] = {}
    db = _FormulaDB()

    async def get_settings(_db, _user):
        return SimpleNamespace(llm_provider="ollama", llm_model="llama3.2")

    def create_client(*, provider: str, model: str, api_key: str | None):
        captured.update(provider=provider, model=model, api_key=api_key)
        return _FormulaClient()

    monkeypatch.setattr(formula_assist_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr("backend.trading_agents.llm_clients.factory.create_llm_client", create_client)
    monkeypatch.setattr(formula_assist_service, "_synthetic_ohlcv", lambda: object())
    monkeypatch.setattr(formula_assist_service, "evaluate_formula_safely", lambda _frame, _formula: None)

    result = await formula_assist_service.generate_formula(db, "20 day moving average", object())

    assert result == "SMA(20)"
    assert captured == {"provider": "ollama", "model": "llama3.2", "api_key": None}
    assert db.commits == 1


@pytest.mark.asyncio
async def test_formula_assist_rejects_cloud_provider_without_tenant_key(monkeypatch):
    async def get_settings(_db, _user):
        return SimpleNamespace(llm_provider="openai", llm_model="gpt-4o-mini")

    def should_not_create_client(**_kwargs):
        pytest.fail("a cloud LLM client must not be created without a tenant key")

    monkeypatch.setattr(formula_assist_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr("backend.trading_agents.llm_clients.factory.create_llm_client", should_not_create_client)

    with pytest.raises(ValueError, match="No API key set for provider 'openai'"):
        await formula_assist_service.generate_formula(_FormulaDB(), "20 day moving average", object())


@pytest.mark.asyncio
async def test_formula_assist_retries_transient_worker_capacity_error(monkeypatch):
    llm = _SequenceFormulaLLM(
        [
            RuntimeError("ResourceExhausted: Worker local total request limit reached (33/32)"),
            SimpleNamespace(content="SMA(20)"),
        ]
    )
    db = _FormulaDB()

    async def get_settings(_db, _user):
        return SimpleNamespace(llm_provider="nvidia", llm_model="test-model")

    monkeypatch.setattr(formula_assist_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: "key")
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _FormulaClient(llm),
    )
    monkeypatch.setattr(formula_assist_service, "_synthetic_ohlcv", lambda: object())
    monkeypatch.setattr(formula_assist_service, "evaluate_formula_safely", lambda _frame, _formula: None)
    monkeypatch.setattr(formula_assist_service, "_LLM_RETRY_BASE_DELAY_SECONDS", 0.0)

    result = await formula_assist_service.generate_formula(db, "20 day moving average", object())

    assert result == "SMA(20)"
    assert llm.calls == 2
    assert db.commits == 1


@pytest.mark.asyncio
async def test_formula_assist_releases_db_before_provider_invocation(monkeypatch):
    db = _FormulaDB()

    class CommitAwareLLM:
        async def ainvoke(self, _messages):
            assert db.commits == 1
            return SimpleNamespace(content="SMA(20)")

    async def get_settings(_db, _user):
        return SimpleNamespace(llm_provider="ollama", llm_model="llama3.2")

    monkeypatch.setattr(formula_assist_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: None)
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _FormulaClient(CommitAwareLLM()),
    )
    monkeypatch.setattr(formula_assist_service, "_synthetic_ohlcv", lambda: object())
    monkeypatch.setattr(formula_assist_service, "evaluate_formula_safely", lambda _frame, _formula: None)

    assert await formula_assist_service.generate_formula(db, "20 day moving average", object()) == "SMA(20)"


@pytest.mark.asyncio
async def test_formula_assist_returns_503_when_worker_capacity_stays_exhausted(monkeypatch):
    error = RuntimeError("ResourceExhausted: Worker local total request limit reached (33/32)")
    llm = _SequenceFormulaLLM([error, error, error])
    db = _FormulaDB()

    async def get_settings(_db, _user):
        return SimpleNamespace(llm_provider="nvidia", llm_model="test-model")

    monkeypatch.setattr(formula_assist_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.services.user_service.resolve_user_api_key", lambda _user, _provider: "key")
    monkeypatch.setattr(
        "backend.trading_agents.llm_clients.factory.create_llm_client",
        lambda **_kwargs: _FormulaClient(llm),
    )
    monkeypatch.setattr(formula_assist_service, "_LLM_RETRY_BASE_DELAY_SECONDS", 0.0)

    with pytest.raises(ExternalServiceError) as exc_info:
        await formula_assist_service.generate_formula(db, "20 day moving average", object())

    assert exc_info.value.status_code == 503
    assert "temporarily at capacity" in exc_info.value.detail
    assert llm.calls == 3
    assert db.commits == 1
