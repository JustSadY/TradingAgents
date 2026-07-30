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
    create_agent_qa_node,
    create_market_intelligence_node,
    create_portfolio_manager_node,
    create_research_manager_node,
    create_risk_debate_node,
    create_trader_node,
)
from backend.trading_agents.agents.runtime.resilience import guard_node

from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

_MARKET_INTELLIGENCE = "Market Intelligence"
_AGENT_QA = "Agent Q&A"
_RESEARCH_MANAGER = "Research Manager"
_TRADER = "Trader"
_RISK_DEBATE = "Risk Debate"
_PORTFOLIO_MANAGER = "Portfolio Manager"


def _market_timeout_multiplier(selected_analysts: list[str] | set[str]) -> float:
    """Return a bounded-by-work timeout multiplier for analyst orchestration.

    ``node_timeout_seconds`` is an individual LLM/tool wall-clock limit.  The
    Market Intelligence coordinator legitimately runs several of those nodes,
    so applying that same limit to its *entire* subgraph cancels healthy work
    halfway through.  The number stays tied to the configured per-node limit,
    while preserving a full sequential-work upper bound.  Team composition
    can be uneven, so dividing by the configured concurrency would be an
    optimistic bound that can still cut a healthy long team short.
    """
    return float(max(2, len(selected_analysts)))


def _research_timeout_multiplier(max_debate_rounds: int) -> float:
    """Budget synthesis, each bull/bear turn, audit, and final judgement."""
    rounds = max(1, int(max_debate_rounds or 1))
    return float(max(2, 3 + (2 * rounds)))


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

    def setup_graph(
        self,
        selected_analysts: list[str] | set[str] = None,
    ) -> StateGraph:
        if selected_analysts is None:
            selected_analysts = ["market", "social", "news", "fundamentals"]

        sync_registry_to_graph()

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

        market_intelligence = guard_node(
            create_market_intelligence_node(ctx),
            name=_MARKET_INTELLIGENCE,
            kind="main",
            fallback=lambda state, exc: {},
            timeout_multiplier=_market_timeout_multiplier(selected_analysts),
            retry_timeouts=False,
        )
        agent_qa = guard_node(
            create_agent_qa_node(ctx),
            name=_AGENT_QA,
            kind="main",
            fallback=lambda state, exc: {},
            timeout_multiplier=2,
            retry_timeouts=False,
        )
        research_manager = guard_node(
            create_research_manager_node(ctx),
            name=_RESEARCH_MANAGER,
            kind="main",
            fallback=lambda state, exc: {
                "investment_debate_state": neutral_invest_debate_state("Research branch error; degraded."),
                "investment_plan": "Research manager unavailable; proceeding with available reports.",
            },
            timeout_multiplier=_research_timeout_multiplier(self.config.get("max_debate_rounds", 1)),
            retry_timeouts=False,
        )
        trader = guard_node(
            create_trader_node(ctx),
            name=_TRADER,
            kind="main",
            fallback=lambda state, exc: {
                "trader_investment_plan": "Trader agent unavailable; deferring to risk debate.",
                "trader_proposal_json": "{}",
            },
            timeout_multiplier=2,
            retry_timeouts=False,
        )
        risk_debate = guard_node(
            create_risk_debate_node(ctx),
            name=_RISK_DEBATE,
            kind="main",
            fallback=lambda state, exc: {
                "risk_debate_state": neutral_risk_debate_state("Risk debate error; degraded."),
            },
            retry_timeouts=False,
        )
        portfolio_manager = guard_node(
            create_portfolio_manager_node(ctx),
            name=_PORTFOLIO_MANAGER,
            kind="decision",
            fallback=lambda state, exc: {
                "final_trade_decision": "Hold — automated fallback: Portfolio Manager unavailable.",
            },
            timeout_multiplier=2,
            retry_timeouts=False,
        )

        workflow = StateGraph(AgentState)
        workflow.add_node(_MARKET_INTELLIGENCE, market_intelligence)
        workflow.add_node(_AGENT_QA, agent_qa)
        workflow.add_node(_RESEARCH_MANAGER, research_manager)
        workflow.add_node(_TRADER, trader)
        workflow.add_node(_RISK_DEBATE, risk_debate)
        workflow.add_node(_PORTFOLIO_MANAGER, portfolio_manager)

        workflow.add_edge(START, _MARKET_INTELLIGENCE)
        workflow.add_edge(_MARKET_INTELLIGENCE, _AGENT_QA)
        workflow.add_edge(_AGENT_QA, _RESEARCH_MANAGER)
        workflow.add_edge(_RESEARCH_MANAGER, _TRADER)
        workflow.add_edge(_TRADER, _RISK_DEBATE)
        workflow.add_edge(_RISK_DEBATE, _PORTFOLIO_MANAGER)
        workflow.add_edge(_PORTFOLIO_MANAGER, END)

        return workflow
