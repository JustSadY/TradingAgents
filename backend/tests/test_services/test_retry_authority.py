from __future__ import annotations

import pytest

from backend.trading_agents.agents.runtime import resilience, structured


class _FakeLLM:
    async def ainvoke(self, prompt):
        return {"prompt": prompt}


@pytest.mark.asyncio
async def test_structured_llm_calls_delegate_to_runtime_retry_authority(monkeypatch):
    captured: dict = {}

    async def fake_retry_call(fn, **kwargs):
        captured.update(kwargs)
        return await fn()

    monkeypatch.setattr(resilience, "retry_call", fake_retry_call)

    result = await structured._retry_llm_call(
        _FakeLLM(),
        {"input": "hello"},
        "market_analyst",
        max_retries=3,
        base_delay=0.25,
        timeout=12.0,
    )

    assert result == {"prompt": {"input": "hello"}}
    assert captured == {
        "label": "llm:market_analyst",
        "attempts": 3,
        "base_delay": 0.25,
        "timeout": 12.0,
    }


@pytest.mark.asyncio
async def test_self_correction_does_not_multiply_runtime_retries(monkeypatch):
    calls: list[dict] = []

    async def fake_retry_call(fn, **kwargs):
        calls.append(kwargs)
        return await fn()

    monkeypatch.setattr(resilience, "retry_call", fake_retry_call)

    class _Schema(structured.BaseModel):
        value: int

    class _CorrectionLLM:
        async def ainvoke(self, prompt):
            return type("Response", (), {"content": '{"value": 7}'})()

    result = await structured.self_correct_structured(
        plain_llm=_CorrectionLLM(),
        schema=_Schema,
        original_prompt="return a number",
        bad_output="bad",
        validation_error="invalid json",
        agent_name="risk_manager",
    )

    assert result == _Schema(value=7)
    assert len(calls) == 1
    assert calls[0]["attempts"] == 1
    assert calls[0]["label"] == "llm:risk_manager:self_correction"
