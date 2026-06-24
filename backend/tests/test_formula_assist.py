"""Tests for natural-language → indicator formula generation."""

from types import SimpleNamespace

import pytest

from backend.services import formula_assist_service as svc


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply

    async def ainvoke(self, messages):
        return SimpleNamespace(content=self.reply)


class FakeClient:
    def __init__(self, reply: str):
        self._llm = FakeLLM(reply)

    def get_llm(self):
        return self._llm


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(reply="(Close - SMA(20)) / STD(20)", api_key="sk-test")

    async def fake_settings(db, user):
        return SimpleNamespace(llm_provider="openai", llm_model="gpt-4o-mini")

    def fake_resolve_key(user, provider):
        return state.api_key

    def fake_create_client(provider, model, api_key=None, **kwargs):
        state.used = (provider, model, api_key)
        return FakeClient(state.reply)

    monkeypatch.setattr(svc, "get_or_create_settings", fake_settings)

    import backend.services.user_service as user_svc
    import backend.trading_agents.llm_clients.factory as factory

    monkeypatch.setattr(user_svc, "resolve_user_api_key", fake_resolve_key)
    monkeypatch.setattr(factory, "create_llm_client", fake_create_client)
    return state


def _user(is_admin=False):
    return SimpleNamespace(id=1, is_admin=is_admin)


async def test_plain_reply_is_validated_and_returned(env):
    formula = await svc.generate_formula(None, "20 günlük ortalamadan sapma", _user())
    assert formula == "(Close - SMA(20)) / STD(20)"
    assert env.used == ("openai", "gpt-4o-mini", "sk-test")


async def test_code_fenced_reply_is_unwrapped(env):
    env.reply = "Here you go:\n```\nEMA(12) - EMA(26)\n```\nEnjoy!"
    assert await svc.generate_formula(None, "macd line", _user()) == "EMA(12) - EMA(26)"


async def test_unsupported_marker_raises(env):
    env.reply = "UNSUPPORTED"
    with pytest.raises(ValueError, match="cannot be expressed"):
        await svc.generate_formula(None, "renko brick count", _user())


async def test_invalid_formula_from_llm_is_rejected(env):
    env.reply = "FOO(close) ** bar"
    with pytest.raises(ValueError, match="invalid formula"):
        await svc.generate_formula(None, "nonsense", _user())


async def test_missing_api_key_fails_for_regular_user(env):
    env.api_key = None
    with pytest.raises(ValueError, match="No API key"):
        await svc.generate_formula(None, "macd", _user(is_admin=False))


async def test_empty_prompt_rejected(env):
    with pytest.raises(ValueError, match="Describe the indicator"):
        await svc.generate_formula(None, "   ", _user())


def test_extract_formula_handles_quotes_and_prose():
    assert svc._extract_formula('"RSI(14)"') == "RSI(14)"
    assert svc._extract_formula("`SMA(50) / Close`") == "SMA(50) / Close"
    assert svc._extract_formula("") == ""
