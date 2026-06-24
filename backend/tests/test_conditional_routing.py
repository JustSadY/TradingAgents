"""Regression tests for registry-driven analyst graph routing.

The per-analyst ``should_continue_<key>`` routers are no longer hand-written on
``ConditionalLogic``; ``sync_registry_to_graph()`` injects one for every
registered analyst from its ``@register_analyst`` declaration. These tests
guard that high-risk wiring: every registered analyst must get a router that
sends pending tool calls to its tool node and finished turns to its clear node.
"""

from types import SimpleNamespace

import backend.bootstrap  # noqa: F401  (engine env defaults; import before trading_agents)
import backend.trading_agents.agents  # noqa: F401 — imports & registers all analyst plugins
from backend.trading_agents.agents.analyst_registry import (
    _REGISTRY,
    list_analysts,
    sync_registry_to_graph,
)
from backend.trading_agents.graph.conditional_logic import ConditionalLogic


def _state_with(tool_calls):
    return {"messages": [SimpleNamespace(tool_calls=tool_calls)]}


def test_all_registered_analysts_get_injected_routers():
    sync_registry_to_graph()
    logic = ConditionalLogic()

    analysts = list_analysts()
    assert len(analysts) >= 12

    for key in analysts:
        reg = _REGISTRY[key]
        router = getattr(logic, f"should_continue_{key}")
        # Pending tool calls -> the analyst's tool node.
        assert router(_state_with([{"name": "x"}])) == reg.tool_node
        # No tool calls -> the analyst's message-clear node.
        assert router(_state_with([])) == reg.clear_node


def test_sync_is_idempotent():
    sync_registry_to_graph()
    first = ConditionalLogic.should_continue_market
    sync_registry_to_graph()
    assert ConditionalLogic.should_continue_market is first


def test_debate_and_risk_routers_unchanged():
    logic = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)

    debate = {"investment_debate_state": {"count": 0, "current_response": "Bull: thesis"}}
    assert logic.should_continue_debate(debate) == "Bear Researcher"
    debate["investment_debate_state"]["count"] = 2
    assert logic.should_continue_debate(debate) == "Research Manager"

    risk = {"risk_debate_state": {"count": 0, "latest_speaker": "Aggressive Analyst"}}
    assert logic.should_continue_risk_analysis(risk) == "Conservative Analyst"
    risk["risk_debate_state"] = {"count": 3, "latest_speaker": "Neutral Analyst"}
    assert logic.should_continue_risk_analysis(risk) == "Portfolio Manager"
