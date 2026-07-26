"""Unit tests for the LLM client subsystem.

Tests are lightweight (no database / app bootstrap needed) and focus on:
  - TokenUsage / TokenUsageTracker
  - Error classification (classify_error, is_quota_exhausted, is_rate_limited)
  - FallbackLLM passthrough and composition
  - Provider registry and factory routing
  - Client model validation
"""

from __future__ import annotations

import pytest

from backend.trading_agents.llm_clients import FallbackLLM, TokenUsage, TokenUsageTracker, classify_error
from backend.trading_agents.llm_clients.base_client import is_quota_exhausted, is_rate_limited
from backend.trading_agents.llm_clients.factory import create_llm_client
from backend.trading_agents.llm_clients.registry import llm_registry

# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_default_zeros(self):
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.total_tokens == 0

    def test_add(self):
        a = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
        b = TokenUsage(input_tokens=5, output_tokens=15, total_tokens=20)
        a.add(b)
        assert a.input_tokens == 15
        assert a.output_tokens == 35
        assert a.total_tokens == 50

    def test_from_response(self):
        class FakeResponse:
            usage_metadata = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

        u = TokenUsage.from_response(FakeResponse())
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total_tokens == 150

    def test_from_response_empty(self):
        class FakeResponse:
            pass

        u = TokenUsage.from_response(FakeResponse())
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.total_tokens == 0


# ---------------------------------------------------------------------------
# TokenUsageTracker
# ---------------------------------------------------------------------------


class TestTokenUsageTracker:
    def test_record_accumulates(self):
        tracker = TokenUsageTracker()

        class FakeResponse1:
            usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

        class FakeResponse2:
            usage_metadata = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}

        tracker.record(FakeResponse1())
        tracker.record(FakeResponse2())

        assert tracker.call_count == 2
        assert tracker.total.input_tokens == 30
        assert tracker.total.output_tokens == 15
        assert tracker.total.total_tokens == 45

    def test_reset(self):
        tracker = TokenUsageTracker()

        class FakeResponse:
            usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

        tracker.record(FakeResponse())
        tracker.reset()

        assert tracker.call_count == 0
        assert tracker.total.total_tokens == 0

    def test_snapshot(self):
        tracker = TokenUsageTracker()

        class FakeResponse:
            usage_metadata = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}

        tracker.record(FakeResponse())
        snap = tracker.snapshot()

        assert snap["input_tokens"] == 7
        assert snap["output_tokens"] == 3
        assert snap["total_tokens"] == 10
        assert snap["llm_calls"] == 1


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    @pytest.mark.parametrize(
        "msg",
        ["ResourceExhausted", "insufficient_quota", "rate_limit_exceeded", "429 Too Many Requests", "quota exceeded"],
    )
    def test_is_quota_exhausted_true(self, msg):
        assert is_quota_exhausted(Exception(msg)) is True

    def test_is_quota_exhausted_false(self):
        assert is_quota_exhausted(Exception("some other error")) is False

    @pytest.mark.parametrize("msg", ["429", "rate_limit exceeded", "retry after"])
    def test_is_rate_limited_true(self, msg):
        assert is_rate_limited(Exception(msg)) is True

    def test_is_rate_limited_false(self):
        assert is_rate_limited(Exception("some other error")) is False

    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ("resourceexhausted", "quota_exhausted"),
            ("too many requests", "quota_exhausted"),
            ("401 unauthorized", "auth"),
            ("403 forbidden", "auth"),
            ("invalid_api_key", "auth"),
            ("timeout after 30s", "timeout"),
            ("some random error", "unknown"),
            # "429" and "rate limit" hit is_quota_exhausted first
            ("try again later", "rate_limited"),
        ],
    )
    def test_classify_error(self, msg, expected):
        assert classify_error(Exception(msg)) == expected


# ---------------------------------------------------------------------------
# FallbackLLM
# ---------------------------------------------------------------------------


class StubLLM:
    """Minimal stub that mimics the BaseChatModel interface needed by FallbackLLM."""

    def __init__(self, name: str, fail_on_invoke: bool = False):
        self.model_name = name
        self._fail = fail_on_invoke

    def bind_tools(self, tools, **kwargs):
        if self._fail:
            raise RuntimeError(f"{self.model_name} bind_tools failed")
        return _BoundStub(self)

    def with_structured_output(self, schema, **kwargs):
        if self._fail:
            raise RuntimeError(f"{self.model_name} with_structured_output failed")
        return _BoundStub(self)

    def with_config(self, *args, **kwargs):
        return self

    def with_fallbacks(self, fallbacks):
        return _FallbackRunnable(self, fallbacks)

    def invoke(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError(f"{self.model_name} invoke failed")
        return f"{self.model_name} response"

    async def ainvoke(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        yield f"{self.model_name} chunk"

    async def astream(self, *args, **kwargs):
        yield f"{self.model_name} chunk"

    def astream_events(self, *args, **kwargs):
        return iter([{"event": "on_chunk", "data": f"{self.model_name} event"}])


class _BoundStub:
    def __init__(self, llm: StubLLM):
        self._llm = llm

    def with_fallbacks(self, fallbacks):
        extracted = []
        for fb in fallbacks:
            extracted.append(fb._llm if hasattr(fb, "_llm") else fb)
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
    def test_repr(self):
        primary = StubLLM("gpt-4")
        fb = StubLLM("claude-3")
        fallback = FallbackLLM(primary, [fb])
        r = repr(fallback)
        assert "gpt-4" in r
        assert "claude-3" in r

    def test_single_fallback_wrapped_in_list(self):
        primary = StubLLM("gpt-4")
        fb = StubLLM("claude-3")
        fallback = FallbackLLM(primary, fb)
        assert len(fallback.fallbacks) == 1

    def test_bind_tools_drops_failed_fallback(self):
        primary = StubLLM("gpt-4")
        fb_ok = StubLLM("claude-3")
        fb_fail = StubLLM("broken", fail_on_invoke=True)
        fallback = FallbackLLM(primary, [fb_ok, fb_fail])
        result = fallback.bind_tools([])
        assert result is not None

    def test_with_structured_output_drops_failed_fallback(self):
        primary = StubLLM("gpt-4")
        fb_ok = StubLLM("claude-3")
        fb_fail = StubLLM("broken", fail_on_invoke=True)
        fallback = FallbackLLM(primary, [fb_ok, fb_fail])
        result = fallback.with_structured_output(str)
        assert result is not None

    def test_astream_events_passthrough(self):
        primary = StubLLM("gpt-4")
        fallback = FallbackLLM(primary, [])
        events = list(fallback.astream_events())
        assert len(events) == 1
        assert events[0]["event"] == "on_chunk"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_providers_registered(self):
        providers = llm_registry.list_providers()
        keys = {p.key for p in providers}
        for expected in ("openai", "anthropic", "google", "mistral", "groq", "nvidia", "deepseek", "ollama"):
            assert expected in keys, f"Missing provider: {expected}"

    def test_get_provider_labels(self):
        labels = llm_registry.get_provider_labels()
        assert labels["openai"] == "OpenAI"
        assert labels["anthropic"] == "Anthropic (Claude)"
        assert labels["deepseek"] == "DeepSeek"

    def test_get_model_options(self):
        models = llm_registry.get_model_options("openai")
        assert len(models) > 0
        assert any("gpt-4o" in m[1] for m in models)

    def test_is_openai_compatible(self):
        assert llm_registry.is_openai_compatible("openai") is True
        assert llm_registry.is_openai_compatible("nvidia") is True
        assert llm_registry.is_openai_compatible("deepseek") is True
        assert llm_registry.is_openai_compatible("ollama") is True
        assert llm_registry.is_openai_compatible("anthropic") is False
        assert llm_registry.is_openai_compatible("google") is False

    def test_get_effort_options(self):
        efforts = llm_registry.get_effort_options()
        assert "openai" in efforts
        assert "anthropic" in efforts
        assert "google" in efforts


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_create_openai_client(self):
        client = create_llm_client("openai", "gpt-4o", api_key="sk-test")
        assert client.get_provider_name() == "openai"

    def test_create_anthropic_client(self):
        client = create_llm_client("anthropic", "claude-3-5-sonnet-latest", api_key="sk-test")
        assert client.get_provider_name() == "anthropic"

    def test_create_google_client(self):
        client = create_llm_client("google", "gemini-1.5-pro", api_key="test-key")
        assert client.get_provider_name() == "google"

    def test_create_mistral_client(self):
        client = create_llm_client("mistral", "mistral-large-latest", api_key="test-key")
        assert client.get_provider_name() == "mistral"

    def test_create_groq_client(self):
        client = create_llm_client("groq", "llama-3.3-70b-versatile", api_key="gsk-test")
        assert client.get_provider_name() == "groq"

    def test_create_nvidia_openai_compatible(self):
        client = create_llm_client("nvidia", "nvidia/llama-3.1-nemotron-70b-instruct", api_key="nv-test")
        assert client.get_provider_name() == "nvidia"

    def test_create_deepseek_openai_compatible(self):
        client = create_llm_client("deepseek", "deepseek-chat", api_key="sk-test")
        assert client.get_provider_name() == "deepseek"

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client("nonexistent", "some-model", api_key="test")

    def test_openai_client_missing_key_raises(self):
        client = create_llm_client("openai", "gpt-4o")
        with pytest.raises(ValueError, match="API key"):
            client.get_llm()

    def test_openai_client_get_llm_ollama_no_key(self):
        client = create_llm_client("ollama", "llama3.2")
        llm = client.get_llm()
        assert llm is not None

    def test_anthropic_missing_key_raises(self):
        client = create_llm_client("anthropic", "claude-3-5-sonnet-latest")
        with pytest.raises(ValueError, match="API key"):
            client.get_llm()


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestModelValidation:
    def test_validate_known_model(self):
        client = create_llm_client("openai", "gpt-4o", api_key="sk-test")
        assert client.validate_model() is True

    def test_validate_unknown_model(self):
        client = create_llm_client("openai", "nonexistent-model-v99", api_key="sk-test")
        assert client.validate_model() is False

    def test_anthropic_known_model(self):
        client = create_llm_client("anthropic", "claude-3-5-sonnet-latest", api_key="sk-test")
        assert client.validate_model() is True
