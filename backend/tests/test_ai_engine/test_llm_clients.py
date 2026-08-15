"""Unit tests for the unified LLM client subsystem."""

from __future__ import annotations

import pytest

from backend.trading_agents.llm_clients import FallbackLLM, TokenUsage, TokenUsageTracker, classify_error
from backend.trading_agents.llm_clients.base_client import is_quota_exhausted, is_rate_limited
from backend.trading_agents.llm_clients.factory import create_llm_client
from backend.trading_agents.llm_clients.litellm_client import LiteLLMClient, routed_model
from backend.trading_agents.llm_clients.registry import llm_registry, provider_requires_api_key


class TestTokenUsage:
    def test_default_zeros(self):
        assert TokenUsage() == TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)

    def test_add(self):
        total = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        total.add(TokenUsage(input_tokens=5, output_tokens=15, total_tokens=20))
        assert (total.input_tokens, total.output_tokens, total.total_tokens) == (15, 35, 50)

    def test_from_response(self):
        class FakeResponse:
            usage_metadata = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

        assert TokenUsage.from_response(FakeResponse()).total_tokens == 150


class TestTokenUsageTracker:
    def test_record_reset_and_snapshot(self):
        tracker = TokenUsageTracker()

        class FakeResponse:
            usage_metadata = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}

        tracker.record(FakeResponse())
        assert tracker.snapshot() == {
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
            "llm_calls": 1,
        }
        tracker.reset()
        assert tracker.call_count == 0
        assert tracker.total.total_tokens == 0


class TestErrorClassification:
    @pytest.mark.parametrize(
        "msg",
        ["ResourceExhausted", "insufficient_quota", "rate_limit_exceeded", "429 Too Many Requests", "quota exceeded"],
    )
    def test_is_quota_exhausted_true(self, msg):
        assert is_quota_exhausted(Exception(msg)) is True

    @pytest.mark.parametrize("msg", ["429", "rate_limit exceeded", "retry after"])
    def test_is_rate_limited_true(self, msg):
        assert is_rate_limited(Exception(msg)) is True

    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ("resourceexhausted", "quota"),
            ("401 unauthorized", "auth"),
            ("timeout after 30s", "timeout"),
            ("some random error", "bug"),
        ],
    )
    def test_classify_error(self, msg, expected):
        assert classify_error(Exception(msg)) == expected


class StubLLM:
    def __init__(self, name: str, fail_on_invoke: bool = False):
        self.model_name = name
        self._fail = fail_on_invoke

    def bind_tools(self, tools, **kwargs):
        if self._fail:
            raise RuntimeError("bind_tools failed")
        return _BoundStub(self)

    def with_structured_output(self, schema, **kwargs):
        if self._fail:
            raise RuntimeError("structured output failed")
        return _BoundStub(self)

    def with_config(self, *args, **kwargs):
        return self

    def with_fallbacks(self, fallbacks):
        return _FallbackRunnable(self, fallbacks)

    def invoke(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError("invoke failed")
        return f"{self.model_name} response"

    async def ainvoke(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        yield f"{self.model_name} chunk"

    async def astream(self, *args, **kwargs):
        yield f"{self.model_name} chunk"

    def astream_events(self, *args, **kwargs):
        return iter([{"event": "on_chunk"}])


class _BoundStub:
    def __init__(self, llm: StubLLM):
        self._llm = llm

    def with_fallbacks(self, fallbacks):
        extracted = [fb._llm if hasattr(fb, "_llm") else fb for fb in fallbacks]
        return _FallbackRunnable(self._llm, extracted)


class _FallbackRunnable:
    def __init__(self, primary, fallbacks):
        self._primary = primary
        self._fallbacks = fallbacks

    def invoke(self, *args, **kwargs):
        return self._primary.invoke(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        return await self._primary.ainvoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._primary.stream(*args, **kwargs)

    async def astream(self, *args, **kwargs):
        return self._primary.astream(*args, **kwargs)

    def astream_events(self, *args, **kwargs):
        return self._primary.astream_events(*args, **kwargs)


class TestFallbackLLM:
    def test_repr_and_binding(self):
        primary = StubLLM("primary")
        fallback = FallbackLLM(primary, [StubLLM("backup")])
        assert "primary" in repr(fallback)
        assert fallback.bind_tools([]) is not None
        assert fallback.with_structured_output(str) is not None


class TestRegistry:
    def test_all_providers_registered(self):
        keys = {p.key for p in llm_registry.list_providers()}
        assert keys == {"openai", "anthropic", "google", "mistral", "groq", "nvidia", "deepseek", "ollama"}

    def test_provider_credential_policy(self):
        assert provider_requires_api_key("ollama") is False
        assert provider_requires_api_key("openai") is True


class TestFactory:
    @pytest.mark.parametrize(
        ("provider", "model", "expected_route"),
        [
            ("openai", "gpt-5.6-sol", "openai/gpt-5.6-sol"),
            ("anthropic", "claude-sonnet-5", "anthropic/claude-sonnet-5"),
            ("google", "gemini-3.7-flash", "gemini/gemini-3.7-flash"),
            ("mistral", "mistral-large-3-25-12", "mistral/mistral-large-3-25-12"),
            ("groq", "openai/gpt-oss-120b", "groq/openai/gpt-oss-120b"),
            ("nvidia", "meta/llama-3.1-70b-instruct", "nvidia_nim/meta/llama-3.1-70b-instruct"),
            ("deepseek", "deepseek-v4-flash", "deepseek/deepseek-v4-flash"),
        ],
    )
    def test_every_hosted_provider_uses_litellm(self, provider, model, expected_route):
        client = create_llm_client(provider, model, api_key="test-key")
        assert isinstance(client, LiteLLMClient)
        assert client.model == expected_route
        assert client.get_provider_name() == "litellm"

    def test_ollama_uses_litellm_route(self, monkeypatch):
        from backend.core import config as config_module

        monkeypatch.setattr(config_module, "get_settings", lambda: type("S", (), {"OLLAMA_BASE_URL": "http://localhost:11434"})())
        client = create_llm_client("ollama", "qwen3.6:27b")
        assert isinstance(client, LiteLLMClient)
        assert client.model == "ollama/qwen3.6:27b"
        assert client.base_url == "http://localhost:11434"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client("nonexistent", "some-model")

    def test_routes_are_owned_by_litellm_mapping(self):
        assert routed_model("google", "gemini-3.7-flash") == "gemini/gemini-3.7-flash"
        assert routed_model("nvidia", "nvidia/nemotron") == "nvidia_nim/nvidia/nemotron"


class TestSingleRetryAuthority:
    def test_sdk_retries_are_disabled_by_default(self, monkeypatch):
        from backend.trading_agents.llm_clients import litellm_client

        captured = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(litellm_client, "GuardedChatLiteLLM", FakeChat)
        create_llm_client("openai", "gpt-5.6-sol", api_key="test").get_llm()
        assert captured["max_retries"] == 0

    def test_explicit_retry_setting_wins(self, monkeypatch):
        from backend.trading_agents.llm_clients import litellm_client

        captured = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(litellm_client, "GuardedChatLiteLLM", FakeChat)
        create_llm_client("openai", "gpt-5.6-sol", api_key="test", max_retries=3).get_llm()
        assert captured["max_retries"] == 3
