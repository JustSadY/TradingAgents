"""Regressions for non-silent analyst report degradation.

The Market Intelligence stage runs analyst subgraphs, and a provider can also
return a syntactically valid response with no readable content.  Neither case
may leave a selected analyst as a blank, indistinguishable UI/report section.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _MarketContext:
    def __init__(self, selected_analysts: list[str], *, concurrency: int) -> None:
        self.selected_analysts = selected_analysts
        self.config = {
            "analyst_concurrency_limit": concurrency,
            "max_recur_limit": 25,
        }

    def is_enabled(self, _key: str) -> bool:
        return True


class _Subgraph:
    def __init__(self, result: dict) -> None:
        self._result = result

    async def ainvoke(self, _state, *, config):
        assert config["recursion_limit"] == 25
        return self._result


@pytest.mark.asyncio
async def test_parallel_team_failure_keeps_healthy_team_report_and_marks_only_failed_team(monkeypatch):
    from backend.trading_agents.agents.main import market_intelligence

    def build_subgraph(keys, _ctx):
        if keys == ["market"]:
            raise RuntimeError("bad team graph")
        assert keys == ["news"]
        return _Subgraph({"news_report": "Healthy news report"})

    monkeypatch.setattr(market_intelligence, "_build_analyst_subgraph", build_subgraph)

    node = market_intelligence.create_market_intelligence_node(_MarketContext(["market", "news"], concurrency=2))
    result = await node({"messages": []})

    assert result["news_report"] == "Healthy news report"
    assert result["market_report"].startswith("⚠️ Market Analyst analysis unavailable:")
    assert "RuntimeError" in result["market_report"]
    assert "news_report" not in result or result["news_report"] == "Healthy news report"


@pytest.mark.asyncio
async def test_parallel_teams_do_not_blank_each_other_with_unowned_report_keys(monkeypatch):
    """A team's result must not carry — and overwrite — a sibling's report key.

    Every subgraph runs on a copy of the full run state, whose schema seeds all
    report fields with ``""``.  Merging those foreign blanks used to leave only
    the last team's reports, silently wiping every earlier team's analysis.
    """
    from backend.trading_agents.agents.analyst_registry import all_report_keys
    from backend.trading_agents.agents.main import market_intelligence

    def build_subgraph(keys, _ctx):
        # Mirror LangGraph: the result echoes the whole seeded state schema.
        result = dict.fromkeys(all_report_keys(), "")
        for key in keys:
            result[market_intelligence.report_key_for(key)] = f"{key} report"
        return _Subgraph(result)

    monkeypatch.setattr(market_intelligence, "_build_analyst_subgraph", build_subgraph)

    # market → "technical", news → "macro_sentiment", ratings → "extra" (last).
    selected = ["market", "news", "ratings"]
    node = market_intelligence.create_market_intelligence_node(_MarketContext(selected, concurrency=3))
    result = await node({"messages": []})

    assert result == {
        "market_report": "market report",
        "news_report": "news report",
        "ratings_report": "ratings report",
    }


@pytest.mark.asyncio
async def test_sequential_subgraph_failure_is_visible_instead_of_silent_blank(monkeypatch):
    from backend.trading_agents.agents.main import market_intelligence

    def build_subgraph(_keys, _ctx):
        raise RuntimeError("bad graph")

    monkeypatch.setattr(market_intelligence, "_build_analyst_subgraph", build_subgraph)

    node = market_intelligence.create_market_intelligence_node(_MarketContext(["fundamentals"], concurrency=1))
    result = await node({"messages": []})

    assert result["fundamentals_report"].startswith("⚠️ Fundamentals Analyst analysis unavailable:")


@pytest.mark.asyncio
async def test_sentiment_uses_shared_visible_empty_report_fallback_and_does_not_cache_it(monkeypatch):
    from backend.trading_agents.agents.sub.analysts import sentiment_analyst

    async def route_to_vendor(_method, *_args, **_kwargs):
        return "source data"

    async def no_cache(*_args, **_kwargs):
        return None

    cached: list[str] = []

    async def cache_report(*_args, **_kwargs):
        cached.append("called")

    captured: dict = {}

    async def shared_runner(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "messages": [],
            "sentiment_report": "⚠️ Sentiment analysis unavailable: the selected model returned no readable final report.",
        }

    monkeypatch.setattr(sentiment_analyst, "route_to_vendor", route_to_vendor)
    monkeypatch.setattr(sentiment_analyst, "check_analyst_cache", no_cache)
    monkeypatch.setattr(sentiment_analyst, "store_analyst_cache", cache_report)
    monkeypatch.setattr(sentiment_analyst, "run_tool_analyst", shared_runner)

    result = await sentiment_analyst.create_sentiment_analyst(object())(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2026-08-01",
            "messages": [],
        }
    )

    assert captured["report_key"] == "sentiment_report"
    assert captured["tools"] == []
    assert result["sentiment_report"].startswith("⚠️ Sentiment analysis unavailable:")
    assert cached == []


@pytest.mark.asyncio
async def test_review_uses_shared_visible_empty_report_fallback_and_does_not_cache_it(monkeypatch):
    from backend.trading_agents.agents.sub.analysts import review_analyst

    async def no_cache(*_args, **_kwargs):
        return None

    cached: list[str] = []

    async def cache_report(*_args, **_kwargs):
        cached.append("called")

    async def performance_data(_payload):
        return "No past analysis data available for hindsight review."

    captured: dict = {}

    async def shared_runner(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "messages": [],
            "review_report": "⚠️ Review analysis unavailable: the selected model returned no readable final report.",
        }

    monkeypatch.setattr(review_analyst, "check_analyst_cache", no_cache)
    monkeypatch.setattr(review_analyst, "store_analyst_cache", cache_report)
    monkeypatch.setattr(
        review_analyst,
        "get_past_performance_data",
        SimpleNamespace(ainvoke=performance_data),
    )
    monkeypatch.setattr(review_analyst, "run_tool_analyst", shared_runner)

    result = await review_analyst.create_review_analyst(object())(
        {
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "trade_date": "2026-08-01",
            "messages": [],
        }
    )

    assert captured["report_key"] == "review_report"
    assert captured["tools"] == review_analyst._REVIEW_TOOLS
    assert result["review_report"].startswith("⚠️ Review analysis unavailable:")
    assert cached == []


def test_market_intelligence_outer_fallback_marks_all_selected_reports_visible():
    from backend.trading_agents.agents.main.market_intelligence import market_intelligence_failure_update

    result = market_intelligence_failure_update(["market", "news"], TimeoutError())

    assert set(result) == {"market_report", "news_report"}
    assert all(value.startswith("⚠️ ") for value in result.values())
    assert all("TimeoutError" in value for value in result.values())


@pytest.mark.asyncio
async def test_shared_runner_resolves_sentiment_report_to_social_runtime_key(monkeypatch):
    """Social settings/tool policy must not be looked up under ``sentiment``."""
    from backend.trading_agents.agents.data.chart_tools import active_run_context
    from backend.trading_agents.agents.runtime import analyst_node_factory, resilience

    class Prompt:
        @classmethod
        def from_messages(cls, _messages):
            return cls()

        def partial(self, **_kwargs):
            return self

        def __or__(self, llm):
            return llm

    class LLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="Sentiment report", tool_calls=[])

    class Graph:
        config = {"runtime_agent_context": {"social": {"settings": {"system_instruction": "social only"}}}}

        def __init__(self):
            self.filtered_for: str | None = None

        def _filter_tools_for_analyst(self, analyst_key, tools):
            self.filtered_for = analyst_key
            return tools

    async def call_once(fn, **_kwargs):
        return await fn()

    graph = Graph()
    monkeypatch.setattr(analyst_node_factory, "ChatPromptTemplate", Prompt)
    monkeypatch.setattr(analyst_node_factory, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(resilience, "retry_call", call_once)

    token = active_run_context.set({"graph": graph})
    try:
        result = await analyst_node_factory.run_tool_analyst(
            LLM(),
            {"company_of_interest": "AAPL", "trade_date": "2026-08-01", "messages": []},
            tools=[],
            system_message="default",
            report_key="sentiment_report",
            instrument_context="context",
        )
    finally:
        active_run_context.reset(token)

    assert graph.filtered_for == "social"
    assert result["sentiment_report"] == "Sentiment report"
