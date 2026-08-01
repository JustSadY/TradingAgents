"""Regressions for the Portfolio Manager as the single execution authority."""

from __future__ import annotations

import json

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


@pytest.mark.asyncio
async def test_legacy_trader_factory_is_a_safe_noop_not_a_second_llm_authority():
    from backend.trading_agents.agents.sub.trader.trader import create_trader

    result = await create_trader(object())({"investment_plan": "ignored"})

    assert result == {
        "trader_investment_plan": "",
        "trader_proposal_json": "{}",
        "sender": "Legacy Trader",
    }


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
            # Deliberately dangerous legacy advice: it must not reach the PM prompt.
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
