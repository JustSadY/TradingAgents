"""
Main Agent: Market Intelligence.

Owns the analyst sub-agents (market, social, news, fundamentals, macro,
options, quant, earnings, review). Each analyst is a tool-using Tier-2
sub-agent. To reuse the proven analyst+ToolNode mechanics unchanged, this main
node builds a small analyst *subgraph* (exactly the analyst chain the old flat
graph used) and invokes it; the only thing layered on top is the kill-switch
and per-analyst enable filtering.

Kill-switch behaviour:
  • market_intelligence disabled            → return nothing; every analyst
    report stays at its empty default (zero tokens, no tool calls).
  • a single analyst disabled               → it is dropped from the subgraph;
    the others still run.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.graph import END, START, StateGraph

from backend.trading_agents.agents.analyst_registry import get_factory, sync_registry_to_graph
from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.agent_states import AgentState
from backend.trading_agents.agents.runtime.resilience import guard_node
from backend.trading_agents.agents.utils.agent_utils import create_msg_delete

logger = logging.getLogger(__name__)

MAIN_KEY = "market_intelligence"

REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "macro_report",
    "options_report",
    "quant_report",
    "earnings_report",
    "review_report",
)


def _fb_analyst(report_key: str):
    def fb(state, exc):
        from langchain_core.messages import AIMessage

        analyst = report_key.replace("_report", "").title()
        return {
            "messages": [AIMessage(content="")],
            report_key: f"⚠️ {analyst} analysis unavailable (agent error: {exc}).",
        }

    return fb


def _build_analyst_subgraph(enabled_keys: list[str], ctx: AgentRunContext):
    """
    Build & compile the analyst chain for *enabled_keys*.

    Mirrors the analyst section of the original GraphSetup, but terminates at
    END instead of handing off to the Synthesis Manager. Reuses each analyst's
    registered factory, its ToolNode, the auto-generated ConditionalLogic
    router and the message-clear node — so the analyst/tool behaviour is
    byte-for-byte the proven path.
    """
    # Imported lazily: graph/__init__ pulls in graph.setup, which imports this
    # package — a top-level import here would create an agents.main ↔ graph cycle.
    from backend.trading_agents.graph.analyst_execution import build_analyst_execution_plan

    sync_registry_to_graph()
    plan = build_analyst_execution_plan(
        enabled_keys,
        concurrency_limit=ctx.config.get("analyst_concurrency_limit", 1),
    )
    workflow = StateGraph(AgentState)

    for spec in plan.specs:
        _add_analyst_nodes(workflow, spec, ctx)

    # Sequential chain: each analyst runs, clears the shared message buffer, then
    # hands off to the next. (Parallel mode no longer uses this single shared-state
    # graph — see _build_single_analyst_subgraph — because concurrent message
    # clears on one ``messages`` channel race with each other.)
    for i, spec in enumerate(plan.specs):
        if i == 0:
            workflow.add_edge(START, spec.agent_node)
        else:
            workflow.add_edge(plan.specs[i - 1].clear_node, spec.agent_node)
        workflow.add_conditional_edges(
            spec.agent_node,
            getattr(ctx.conditional_logic, f"should_continue_{spec.key}"),
            [spec.tool_node, spec.clear_node],
        )
        workflow.add_edge(spec.tool_node, spec.agent_node)
    if plan.specs:
        workflow.add_edge(plan.specs[-1].clear_node, END)

    return workflow.compile()


def _add_analyst_nodes(workflow, spec, ctx: AgentRunContext) -> None:
    """Register one analyst's agent/clear/tool nodes on *workflow*."""
    factory = get_factory(spec.key)
    node = guard_node(
        factory(ctx.llm_for(spec.key)),
        name=spec.agent_node,
        kind="analyst",
        fallback=_fb_analyst(spec.report_key),
    )
    workflow.add_node(spec.agent_node, node)
    workflow.add_node(spec.clear_node, create_msg_delete())
    workflow.add_node(spec.tool_node, ctx.tool_nodes[spec.key])


def _build_single_analyst_subgraph(spec, ctx: AgentRunContext):
    """Compile an isolated one-analyst chain (agent ↔ tools, then clear → END).

    Used in parallel mode so each analyst runs over its own ``messages`` channel
    and the per-analyst message clears can never race with one another.
    """
    sync_registry_to_graph()
    workflow = StateGraph(AgentState)
    _add_analyst_nodes(workflow, spec, ctx)
    workflow.add_edge(START, spec.agent_node)
    workflow.add_conditional_edges(
        spec.agent_node,
        getattr(ctx.conditional_logic, f"should_continue_{spec.key}"),
        [spec.tool_node, spec.clear_node],
    )
    workflow.add_edge(spec.tool_node, spec.agent_node)
    workflow.add_edge(spec.clear_node, END)
    return workflow.compile()


def create_market_intelligence_node(ctx: AgentRunContext) -> NodeFn:
    async def market_intelligence_node(state) -> dict:
        # Tier-1 kill-switch — disable the whole analyst branch.
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[market_intelligence] branch disabled — skipping all analysts.")
            return {}

        enabled = [k for k in ctx.selected_analysts if ctx.is_enabled(k)]
        skipped = [k for k in ctx.selected_analysts if not ctx.is_enabled(k)]
        if skipped:
            logger.info("[market_intelligence] disabled analysts skipped: %s", skipped)
        if not enabled:
            logger.info("[market_intelligence] no enabled analysts — nothing to run.")
            return {}

        recur = ctx.config.get("max_recur_limit", 100)
        concurrency = ctx.config.get("analyst_concurrency_limit", 1)

        if concurrency <= 1 or len(enabled) <= 1:
            # Sequential: one shared-state subgraph, analysts run back-to-back.
            subgraph = _build_analyst_subgraph(enabled, ctx)
            result = await subgraph.ainvoke(state, config={"recursion_limit": recur})
            return {rk: result.get(rk, "") for rk in REPORT_KEYS if rk in result}

        # Parallel: run each analyst as an isolated subgraph over its own copy of
        # ``messages`` so the per-analyst message clears never race. Each analyst
        # only writes its own report key, so merging the results is conflict-free.
        from backend.trading_agents.graph.analyst_execution import build_analyst_execution_plan

        plan = build_analyst_execution_plan(enabled, concurrency_limit=concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_analyst(spec) -> dict:
            async with semaphore:
                sub = _build_single_analyst_subgraph(spec, ctx)
                analyst_state = {**state, "messages": list(state.get("messages", []))}
                res = await sub.ainvoke(analyst_state, config={"recursion_limit": recur})
                return {rk: res.get(rk, "") for rk in REPORT_KEYS if rk in res}

        results = await asyncio.gather(*[_run_analyst(spec) for spec in plan.specs])
        merged: dict = {}
        for r in results:
            merged.update(r)
        return merged

    return market_intelligence_node
