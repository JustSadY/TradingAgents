"""Regressions for the Portfolio Manager as sole AI proposal authority and canonical execution decisions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.trading_agents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchBias,
    ResearchPlan,
    render_research_plan,
)


def test_research_plan_is_evidence_only_not_an_executable_rating():
    schema = ResearchPlan.model_json_schema()
    properties = schema["properties"]

    assert "research_bias" in properties
    assert "recommendation" not in properties
    assert {"entry_price", "stop_loss", "take_profit_price", "position_size_pct"}.isdisjoint(properties)

    rendered = render_research_plan(
        ResearchPlan(
            research_bias=ResearchBias.BULLISH,
            rationale="The verified evidence leans constructive.",
            key_evidence="Revenue growth and cash conversion improved.",
            risk_conditions="Guidance or demand deterioration invalidates the view.",
        )
    )
    assert "Research Bias" in rendered
    assert "Recommendation" not in rendered

def test_portfolio_decision_exposes_the_complete_canonical_execution_contract():
    decision = PortfolioDecision(
        rating=PortfolioRating.BUY,
        executive_summary="Enter only at the planned level.",
        investment_thesis="The evidence outweighs the defined downside.",
        confidence_score=0.72,
        entry_price=100.0,
        stop_loss=94.0,
        take_profit_price=115.0,
        position_size_pct=7.5,
        suggested_capital=7_500.0,
        recommended_leverage=1.0,
    )

    assert decision.model_dump(mode="json") == {
        "rating": "Buy",
        "executive_summary": "Enter only at the planned level.",
        "investment_thesis": "The evidence outweighs the defined downside.",
        "confidence_score": 0.72,
        "entry_price": 100.0,
        "stop_loss": 94.0,
        "take_profit_price": 115.0,
        "position_size_pct": 7.5,
        "suggested_capital": 7500.0,
        "price_target": None,
        "recommended_leverage": 1.0,
        "liquidation_price": None,
        "time_horizon": None,
    }

def test_active_graph_state_excludes_retired_trader_execution_fields():
    from backend.trading_agents.agents.runtime.agent_states import AgentState, StateKeys

    assert "trader_investment_plan" not in AgentState.__annotations__
    assert "trader_proposal_json" not in AgentState.__annotations__
    assert not hasattr(StateKeys, "TRADER_INVESTMENT_PLAN")
    assert not hasattr(StateKeys, "TRADER_PROPOSAL_JSON")

def test_multi_ticker_overview_is_deterministic_and_non_executing():
    from backend.services.analysis.portfolio_orchestrator import build_portfolio_overview

    overview = build_portfolio_overview(
        {
            "NVDA": {"portfolio_decision": "**Rating**: Buy\n**Position Sizing**: 5.0%"},
            "AAPL": {"portfolio_decision": "**Rating**: Hold"},
        },
        portfolio_context="Cash available: $10,000.",
    )

    assert "This overview does not create or amend a buy/sell order" in overview
    assert "Canonical Final Decision" in overview
    assert "sole execution input" in overview
    assert "## AAPL" in overview
    assert "## NVDA" in overview
    assert "**Rating**: Buy" in overview
    assert "this multi-ticker overview cannot place an order or change a quantity" in overview

def test_performance_review_prefers_prior_canonical_decision_over_legacy_trader_text():
    from backend.trading_agents.agents.data.review_tools import _past_decision_for_review

    decision, label = _past_decision_for_review(
        SimpleNamespace(
            final_decision="**Rating**: Hold",
            trader_plan="SELL EVERYTHING",
        )
    )

    assert decision == "**Rating**: Hold"
    assert label == "PAST CANONICAL FINAL DECISION"

def test_portfolio_manager_evidence_tracks_registry_reports_and_supplemental_artifacts(monkeypatch):
    from backend.trading_agents.agents import analyst_registry
    from backend.trading_agents.agents.sub.managers import portfolio_manager as pm

    monkeypatch.setattr(analyst_registry, "get_report_fields", lambda: {"new_plugin_report": "New Plugin Analyst"})
    packet = pm.build_portfolio_manager_evidence(
        {
            "new_plugin_report": "## Executive Summary\nThe new active analyst found a catalyst.",
            "synthesis_report": "The synthesis reconciled the catalyst with valuation risk.",
            "audit_report": "The auditor confirmed the cited numbers.",
            "agent_qa_report": "The analysts resolved their disagreement.",
        }
    )

    assert "New Plugin Analyst" in packet
    assert "new active analyst found a catalyst" in packet.lower()
    assert "Synthesis Manager Conflict Map" in packet
    assert "Auditor Fact Check" in packet
    assert "Analyst Cross-Examination" in packet

@pytest.mark.asyncio
async def test_portfolio_manager_ignores_legacy_trader_plan_and_emits_canonical_json(monkeypatch):
    from backend.services import memory_service
    from backend.trading_agents.agents import analyst_registry
    from backend.trading_agents.agents.runtime import portfolio_context
    from backend.trading_agents.agents.sub.managers import portfolio_manager as pm
    from backend.trading_agents.dataflows import config

    captured: dict[str, str] = {}
    final = PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT,
        executive_summary="Increase only to a measured target allocation.",
        investment_thesis="The complete evidence packet is constructive but not risk-free.",
        confidence_score=0.68,
        entry_price=101.0,
        stop_loss=95.0,
        take_profit_price=116.0,
        position_size_pct=6.0,
        suggested_capital=6000.0,
        recommended_leverage=1.0,
    )

    async def fake_structured(_structured, _plain, prompt, _name, *, schema):
        assert schema is PortfolioDecision
        captured["prompt"] = prompt
        return final

    async def no_memory(**_kwargs):
        return ""

    async def fake_portfolio_context(_user_id):
        return "Portfolio: cash available 100,000; existing NVDA holding 0."

    monkeypatch.setattr(pm, "bind_structured", lambda *_args: None)
    monkeypatch.setattr(pm, "ainvoke_structured_or_freetext", fake_structured)
    monkeypatch.setattr(pm, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(pm, "get_system_instruction_override", lambda _key: None)
    monkeypatch.setattr(config, "get_config", lambda: {"user_id": 1, "investor_persona": "Balanced"})
    monkeypatch.setattr(memory_service, "recall_episode_lessons", no_memory)
    monkeypatch.setattr(portfolio_context, "get_portfolio_context", fake_portfolio_context)
    monkeypatch.setattr(analyst_registry, "get_report_fields", lambda: {"new_plugin_report": "New Plugin Analyst"})

    node = pm.create_portfolio_manager(object())
    result = await node(
        {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "investment_plan": "Research posture: bullish, with an earnings invalidation condition.",
            "trader_investment_plan": "SELL ALL NVDA AT ANY PRICE.",
            "new_plugin_report": "## Executive Summary\nNew active analyst supports a measured entry.",
            "risk_debate_state": {
                "history": "Conservative Analyst: Respect the stop.",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "count": 1,
            },
        }
    )

    assert result["final_signal"] == "Overweight"
    assert json.loads(result["portfolio_decision_json"])["position_size_pct"] == 6.0
    assert "SELL ALL NVDA AT ANY PRICE" not in captured["prompt"]
    assert "New Plugin Analyst" in captured["prompt"]
    assert "only** agent allowed to produce a final Buy" in captured["prompt"]


@pytest.mark.asyncio
async def test_portfolio_manager_excludes_live_portfolio_for_same_day_time_travel(monkeypatch):
    """A checkpoint replay is historical even if its business date is today."""

    from backend.services import memory_service
    from backend.trading_agents.agents.runtime import portfolio_context
    from backend.trading_agents.agents.sub.managers import portfolio_manager as pm
    from backend.trading_agents.dataflows import config

    captured: dict[str, str] = {}
    final = PortfolioDecision(
        rating=PortfolioRating.HOLD,
        executive_summary="No new position is required for this replay.",
        investment_thesis="The replay must not rely on present-day account balances.",
        confidence_score=0.55,
        suggested_capital=0.0,
    )

    async def fake_structured(_structured, _plain, prompt, _name, *, schema):
        assert schema is PortfolioDecision
        captured["prompt"] = prompt
        return final

    async def no_memory(**_kwargs):
        return ""

    async def live_portfolio_must_not_be_read(*_args, **_kwargs):
        raise AssertionError("time-travel must not read mutable live portfolio state")

    monkeypatch.setattr(pm, "bind_structured", lambda *_args: None)
    monkeypatch.setattr(pm, "ainvoke_structured_or_freetext", fake_structured)
    monkeypatch.setattr(pm, "get_general_settings_block", lambda: "")
    monkeypatch.setattr(pm, "get_system_instruction_override", lambda _key: None)
    monkeypatch.setattr(
        config,
        "get_config",
        lambda: {"user_id": 1, "investor_persona": "Balanced", "historical_mode": True},
    )
    monkeypatch.setattr(memory_service, "recall_episode_lessons", no_memory)
    monkeypatch.setattr(portfolio_context, "get_portfolio_context", live_portfolio_must_not_be_read)

    node = pm.create_portfolio_manager(object())
    await node(
        {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            # A same-day date is the regression: date-only filtering would
            # previously treat it as safe to pull the current account.
            "trade_date": "2026-08-08",
            "investment_plan": "Re-evaluate the prior evidence without current account state.",
            "risk_debate_state": {},
        }
    )

    assert "PORTFOLIO CONTEXT EXCLUDED" in captured["prompt"]
    assert "mutable current portfolio must not influence" in captured["prompt"]
