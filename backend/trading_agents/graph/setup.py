"""
Top-level graph assembly for the 3-tier agent model.

The graph now has exactly five nodes — one per Main Agent — wired linearly:

    START → Market Intelligence → Research Manager → Trader
          → Risk Debate → Portfolio Manager → END

Each Main Agent node internally checks its kill-switch and orchestrates its own
Tier-2 sub-agents (which in turn call Tier-3 tools). All of the per-analyst
ToolNode / message-clear / conditional-edge plumbing now lives *inside* the
Market Intelligence node's analyst subgraph, so it no longer clutters the
top-level graph.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.trading_agents.agents import AgentState
from backend.trading_agents.agents.analyst_registry import sync_registry_to_graph
from backend.trading_agents.agents.base import (
    AgentRunContext,
    neutral_invest_debate_state,
    neutral_risk_debate_state,
)
from backend.trading_agents.agents.main import (
    create_market_intelligence_node,
    create_portfolio_manager_node,
    create_research_manager_node,
    create_risk_debate_node,
    create_trader_node,
)
from backend.trading_agents.agents.runtime.resilience import guard_node

from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)


class GraphSetup:
    def __init__(
        self,
        llm: Any,
        tool_nodes: dict[str, Any],
        conditional_logic: ConditionalLogic,
        analyst_concurrency_limit: int = 1,
        agent_llms: dict[str, Any] = None,
        agent_hierarchy=None,
        config: dict[str, Any] = None,
    ):
        self.llm = llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.analyst_concurrency_limit = analyst_concurrency_limit
        self.agent_llms = agent_llms or {}
        self.agent_hierarchy = agent_hierarchy
        self.config = config or {}

    def setup_graph(self, selected_analysts=None):
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]

        sync_registry_to_graph()

        # Shared, read-only context handed to every main node.
        run_config = dict(self.config)
        run_config.setdefault("analyst_concurrency_limit", self.analyst_concurrency_limit)
        ctx = AgentRunContext(
            hierarchy=self.agent_hierarchy,
            llms=self.agent_llms,
            fallback_llm=self.llm,
            tool_nodes=self.tool_nodes,
            conditional_logic=self.conditional_logic,
            config=run_config,
            selected_analysts=list(selected_analysts),
        )

        # ---- Main Agent nodes (guard-wrapped for resilience) ----
        market_intelligence = guard_node(
            create_market_intelligence_node(ctx),
            name="Market Intelligence",
            kind="main",
            fallback=lambda state, exc: {},
        )
        research_manager = guard_node(
            create_research_manager_node(ctx),
            name="Research Manager",
            kind="main",
            fallback=lambda state, exc: {
                "investment_debate_state": neutral_invest_debate_state("Research branch error; degraded."),
                "investment_plan": "Research manager unavailable; proceeding with available reports.",
            },
        )
        trader = guard_node(
            create_trader_node(ctx),
            name="Trader",
            kind="main",
            fallback=lambda state, exc: {
                "trader_investment_plan": "Trader agent unavailable; deferring to risk debate.",
                "trader_proposal_json": "{}",
            },
        )
        risk_debate = guard_node(
            create_risk_debate_node(ctx),
            name="Risk Debate",
            kind="main",
            fallback=lambda state, exc: {
                "risk_debate_state": neutral_risk_debate_state("Risk debate error; degraded."),
            },
        )
        portfolio_manager = guard_node(
            create_portfolio_manager_node(ctx),
            name="Portfolio Manager",
            kind="decision",
            fallback=lambda state, exc: {
                "final_trade_decision": "Hold — automated fallback: Portfolio Manager unavailable.",
            },
        )

        # ---- Wire the five main nodes linearly ----
        workflow = StateGraph(AgentState)
        workflow.add_node("Market Intelligence", market_intelligence)
        workflow.add_node("Research Manager", research_manager)
        workflow.add_node("Trader", trader)
        workflow.add_node("Risk Debate", risk_debate)
        workflow.add_node("Portfolio Manager", portfolio_manager)

        workflow.add_edge(START, "Market Intelligence")
        workflow.add_edge("Market Intelligence", "Research Manager")
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risk Debate")
        workflow.add_edge("Risk Debate", "Portfolio Manager")
        workflow.add_edge("Portfolio Manager", END)

        return workflow
