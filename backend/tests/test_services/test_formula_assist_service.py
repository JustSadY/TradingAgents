"""Credential-policy coverage for the formula-assist LLM entry point."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import formula_assist_service

class _FormulaLLM:
    async def ainvoke(self, _messages):
        return SimpleNamespace(content="SMA(20)")

class _FormulaClient:
    def get_llm(self):
        return _FormulaLLM()

@pytest.mark.asyncio
async def test_formula_assist_allows_server_managed_ollama_without_tenant_key(monkeypatch):
    captured: dict[str, str | None] = {}

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

    result = await formula_assist_service.generate_formula(object(), "20 day moving average", object())

    assert result == "SMA(20)"
    assert captured == {"provider": "ollama", "model": "llama3.2", "api_key": None}

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
        await formula_assist_service.generate_formula(object(), "20 day moving average", object())
