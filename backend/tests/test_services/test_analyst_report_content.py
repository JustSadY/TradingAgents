"""Regression coverage for final analyst report content handling.

Provider adapters normally normalise LangChain content blocks before an analyst
sees them, but a bound/fallback runnable can still return block content directly.
The analyst runtime is the last common boundary before a report is persisted, so
it must never store a list, ``None``, or an empty final response as a silent
empty report.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Prompt:
    @classmethod
    def from_messages(cls, _messages):
        return cls()

    def partial(self, **_kwargs):
        return self

    def __or__(self, llm):
        return llm


class _LLM:
    def __init__(self, response):
        self._response = response

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        return self._response


async def _invoke_market_analyst(monkeypatch, response):
    from backend.trading_agents.agents.runtime import analyst_node_factory, resilience

    async def call_once(fn, **_kwargs):
        return await fn()

    monkeypatch.setattr(analyst_node_factory, "ChatPromptTemplate", _Prompt)
    monkeypatch.setattr(analyst_node_factory, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(resilience, "retry_call", call_once)

    return await analyst_node_factory.run_tool_analyst(
        _LLM(response),
        {"company_of_interest": "AAPL", "trade_date": "2026-07-28", "messages": []},
        tools=[],
        system_message="test instructions",
        report_key="market_report",
        instrument_context="test context",
    )


@pytest.mark.asyncio
async def test_tool_analyst_flattens_final_content_blocks_before_persisting_report(monkeypatch):
    response = SimpleNamespace(
        content=[
            {"type": "text", "text": "## Technical summary"},
            {"type": "text", "text": "Price remains above the 50-day moving average."},
        ],
        tool_calls=[],
    )

    result = await _invoke_market_analyst(monkeypatch, response)

    assert result["market_report"] == ("## Technical summary\nPrice remains above the 50-day moving average.")
    assert isinstance(result["market_report"], str)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [None, []])
async def test_tool_analyst_replaces_empty_final_response_with_visible_market_report(monkeypatch, content):
    """An empty final turn must become a diagnosable report, never a blank UI card."""
    response = SimpleNamespace(content=content, tool_calls=[])

    result = await _invoke_market_analyst(monkeypatch, response)

    report = result["market_report"]
    assert isinstance(report, str)
    assert report.strip()
    assert "market" in report.lower()


@pytest.mark.asyncio
async def test_tool_analyst_does_not_publish_empty_fallback_while_waiting_for_tool_result(monkeypatch):
    """A tool-call turn is intermediate; only its final assistant turn is a report."""
    response = SimpleNamespace(content=[], tool_calls=[{"name": "get_stock_data"}])

    result = await _invoke_market_analyst(monkeypatch, response)

    assert result["market_report"] == ""
