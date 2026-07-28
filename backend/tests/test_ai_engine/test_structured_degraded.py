"""Regression tests for hosted-model degradation in structured generation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from backend.trading_agents.agents.runtime.resilience import classify_error, retry_call
from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext
from backend.trading_agents.llm_clients.base_client import is_provider_function_degraded, retry_with_exponential_backoff
from backend.trading_agents.llm_clients.fallback import FallbackLLM

_DEGRADED = "Function id 'ac74040f-9fc9-4c5e-ac74-279ba5161d69': DEGRADED function cannot be invoked"


class _Decision(BaseModel):
    rating: str


class _Response:
    def __init__(self, content: str):
        self.content = content


class _DegradedLLM:
    def __init__(self):
        self.calls = 0
        self.model_name = "degraded-nim-model"

    async def ainvoke(self, _prompt):
        self.calls += 1
        raise RuntimeError(_DEGRADED)


class _UnsupportedStructuredLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _prompt):
        self.calls += 1
        raise RuntimeError("This model does not support function calling.")


class _FreeTextThenDegradedLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _prompt):
        self.calls += 1
        if self.calls == 1:
            return _Response("This is valid free-text, but not JSON.")
        raise RuntimeError(_DEGRADED)


class _SuccessfulFallbackLLM:
    model_name = "healthy-fallback-model"

    def __init__(self):
        self.calls = 0

    def with_fallbacks(self, _fallbacks):
        return self

    async def ainvoke(self, _prompt):
        self.calls += 1
        return _Response('{"rating": "Hold"}')


def test_degraded_function_is_classified_precisely():
    exc = RuntimeError(_DEGRADED)

    assert is_provider_function_degraded(exc) is True
    assert classify_error(exc) == "provider_degraded"
    assert is_provider_function_degraded(RuntimeError("The portfolio is degraded.")) is False


async def test_degraded_structured_call_skips_same_model_freetext_and_correction():
    structured_llm = _DegradedLLM()
    plain_llm = _DegradedLLM()

    with pytest.raises(RuntimeError, match="DEGRADED function"):
        await ainvoke_structured_or_freetext(
            structured_llm,
            plain_llm,
            "Make a decision",
            "Portfolio Manager",
            schema=_Decision,
        )

    assert structured_llm.calls == 1
    assert plain_llm.calls == 0


async def test_non_degraded_structured_error_still_uses_freetext_fallback():
    structured_llm = _UnsupportedStructuredLLM()
    plain_llm = _SuccessfulFallbackLLM()

    result = await ainvoke_structured_or_freetext(
        structured_llm,
        plain_llm,
        "Make a decision",
        "Portfolio Manager",
        schema=_Decision,
    )

    assert result == _Decision(rating="Hold")
    assert structured_llm.calls == 1
    assert plain_llm.calls == 1


async def test_configured_fallback_is_used_for_a_degraded_primary():
    primary = _DegradedLLM()
    fallback = _SuccessfulFallbackLLM()

    response = await FallbackLLM(primary, fallback).ainvoke("Make a decision")

    assert response.content == '{"rating": "Hold"}'
    assert primary.calls == 1
    assert fallback.calls == 1


async def test_degraded_during_correction_stops_second_correction_and_keeps_free_text():
    llm = _FreeTextThenDegradedLLM()

    result = await ainvoke_structured_or_freetext(
        None,
        llm,
        "Make a decision",
        "Portfolio Manager",
        schema=_Decision,
    )

    assert result == "This is valid free-text, but not JSON."
    # One free-text generation plus one failed correction.  The old path made
    # a third request for correction attempt 2.
    assert llm.calls == 2


async def test_node_retry_does_not_repeat_a_degraded_provider_call():
    calls = 0

    async def invoke():
        nonlocal calls
        calls += 1
        raise RuntimeError(_DEGRADED)

    with pytest.raises(RuntimeError, match="DEGRADED function"):
        await retry_call(invoke, label="decision:Portfolio Manager", attempts=3)

    assert calls == 1


async def test_llm_retry_does_not_repeat_a_degraded_provider_call():
    calls = 0

    async def invoke():
        nonlocal calls
        calls += 1
        raise RuntimeError(_DEGRADED)

    with pytest.raises(RuntimeError, match="DEGRADED function"):
        await retry_with_exponential_backoff(invoke, max_retries=3, base_delay=0)

    assert calls == 1
