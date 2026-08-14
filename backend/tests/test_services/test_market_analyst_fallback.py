"""Market Analyst regressions for empty terminal LLM responses."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_market_analyst_preserves_prefetched_data_when_model_report_is_unavailable(monkeypatch):
    """A provider-side blank must not become an empty or permanently cached panel."""
    from backend.trading_agents.agents.runtime import analyst_cache
    from backend.trading_agents.agents.sub.analysts import market_analyst
    from backend.trading_agents.dataflows import interface

    async def fetch_stock_data(method, *args, **_kwargs):
        assert method == "get_stock_data"
        assert args[0] == "AAPL"
        return "Date,Close,Volume\n2026-07-28,212.35,45678900"

    async def fetch_indicators(*_args, **_kwargs):
        return "RSI: 58.4\nMACD: 1.27\n50 SMA: 205.10"

    async def no_cached_report(*_args, **_kwargs):
        return None

    cached_reports: list[str] = []

    async def record_cache(*_args, **_kwargs):
        cached_reports.append("called")

    async def blank_model_notice(*_args, **_kwargs):
        return {
            "messages": [],
            "market_report": ("⚠️ Market analysis unavailable: the selected model returned no readable final report."),
        }

    monkeypatch.setattr(interface, "route_to_vendor", fetch_stock_data)
    monkeypatch.setattr(market_analyst, "collect_indicators", fetch_indicators)
    monkeypatch.setattr(analyst_cache, "check_analyst_cache", no_cached_report)
    monkeypatch.setattr(analyst_cache, "store_analyst_cache", record_cache)
    monkeypatch.setattr(market_analyst, "run_tool_analyst", blank_model_notice)

    node = market_analyst.create_market_analyst(object())
    result = await node(
        {
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "trade_date": "2026-07-28",
            "messages": [],
        }
    )

    report = result["market_report"]
    assert "Market analysis unavailable" in report
    assert "Collected Market Data — AAPL" in report
    assert "2026-07-28,212.35,45678900" in report
    assert "RSI: 58.4" in report
    assert cached_reports == []

@pytest.mark.asyncio
async def test_market_analyst_keeps_report_empty_while_a_tool_call_is_pending(monkeypatch):
    """The data snapshot is only for a terminal empty response, never a tool turn."""
    from backend.trading_agents.agents.runtime import analyst_cache
    from backend.trading_agents.agents.sub.analysts import market_analyst
    from backend.trading_agents.dataflows import interface

    async def fetch_stock_data(*_args, **_kwargs):
        return "price data"

    async def fetch_indicators(*_args, **_kwargs):
        return "indicator data"

    async def no_cached_report(*_args, **_kwargs):
        return None

    cached_reports: list[str] = []

    async def record_cache(*_args, **_kwargs):
        cached_reports.append("called")

    async def pending_tool_call(*_args, **_kwargs):
        return {
            "messages": [SimpleNamespace(tool_calls=[{"name": "get_stock_data"}])],
            "market_report": "",
        }

    monkeypatch.setattr(interface, "route_to_vendor", fetch_stock_data)
    monkeypatch.setattr(market_analyst, "collect_indicators", fetch_indicators)
    monkeypatch.setattr(analyst_cache, "check_analyst_cache", no_cached_report)
    monkeypatch.setattr(analyst_cache, "store_analyst_cache", record_cache)
    monkeypatch.setattr(market_analyst, "run_tool_analyst", pending_tool_call)

    node = market_analyst.create_market_analyst(object())
    result = await node(
        {
            "company_of_interest": "AAPL",
            "asset_type": "stock",
            "trade_date": "2026-07-28",
            "messages": [],
        }
    )

    assert result["market_report"] == ""
    assert cached_reports == []
