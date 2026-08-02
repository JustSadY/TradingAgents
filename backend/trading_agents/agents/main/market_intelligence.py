"""
Main Agent: Market Intelligence.

Owns the analyst sub-agents (market, social, news, fundamentals, macro,
options, quant, earnings, insider, ownership, catalyst, review). Each analyst
is a tool-using Tier-2
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

from backend.trading_agents.agents.analyst_registry import (
    all_report_keys,
    get_factory,
    report_key_for,
    sync_registry_to_graph,
)
from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.agent_states import AgentState
from backend.trading_agents.agents.runtime.analyst_execution import build_analyst_execution_plan
from backend.trading_agents.agents.runtime.resilience import guard_node
from backend.trading_agents.agents.utils.agent_utils import create_msg_delete

logger = logging.getLogger(__name__)

MAIN_KEY = "market_intelligence"

ANALYST_TEAMS: dict[str, list[str]] = {
    "technical": ["market", "quant"],
    "fundamental": ["fundamentals", "earnings", "insider", "ownership"],
    "macro_sentiment": ["macro", "social", "news", "review"],
    "catalyst_options": ["options", "catalyst"],
}


def _report_keys() -> tuple[str, ...]:
    """Analyst report keys, derived from the live registry at call time.

    Computed lazily (not at import) so every registered analyst — including
    insider/ownership/catalyst — is covered, instead of a stale hardcoded list.
    """
    return all_report_keys()


def _group_report_keys(analyst_keys: list[str] | set[str]) -> tuple[str, ...]:
    """Return only the report keys the given analyst group actually writes.

    A subgraph runs on a copy of the *whole* run state, whose schema seeds
    every registered report field with ``""``.  Its result therefore carries
    each sibling group's report key as an empty string.  Returning those
    foreign keys let one group's blanks overwrite another group's finished
    report when the parallel results were merged, so scope the update to the
    group's own analysts.
    """
    keys: list[str] = []
    for analyst_key in analyst_keys:
        report_key = report_key_for(analyst_key)
        if report_key:
            keys.append(report_key)
    return tuple(dict.fromkeys(keys))


def _fb_analyst(report_key: str):
    def fb(state, exc):
        from langchain_core.messages import AIMessage

        analyst = report_key.replace("_report", "").title()
        return {
            "messages": [AIMessage(content="")],
            report_key: f"{analyst} analysis unavailable (agent error: {exc}).",
        }

    return fb


def market_intelligence_failure_update(selected_analysts: list[str] | set[str], exc: BaseException) -> dict[str, str]:
    """Return a visible fallback for every selected analyst report.

    Individual analyst nodes already have their own guard fallback.  This is
    the last-resort boundary for failures *around* those nodes: a malformed
    subgraph, a coordinator timeout, or an unexpected graph-runtime error.
    Without this update the outer Market Intelligence guard returned ``{}``,
    which made every affected selected report look like it never existed.

    Keep the message deliberately generic.  Provider exceptions can contain
    request metadata, so they belong in the server log rather than a report
    shown to the user or placed in a shareable link.
    """
    from backend.trading_agents.agent_catalog import label_for

    error_kind = type(exc).__name__
    updates: dict[str, str] = {}
    for analyst_key in selected_analysts:
        report_key = report_key_for(analyst_key)
        if not report_key:
            continue
        label = label_for(analyst_key)
        updates[report_key] = (
            f"⚠️ {label} analysis unavailable: the Market Intelligence coordinator could not run this "
            f"analyst group ({error_kind}). No conclusion was inferred."
        )
    return updates


async def _run_analyst_subgraph(
    analyst_keys: list[str],
    ctx: AgentRunContext,
    state: dict,
    *,
    recursion_limit: int,
) -> dict:
    """Run one isolated analyst group without erasing its sibling groups.

    Parallel mode intentionally uses several LangGraph subgraphs.  ``gather``
    normally propagates one group's construction/runtime exception and causes
    the outer Market Intelligence guard to return an empty update, which loses
    healthy reports from every other group.  Turn a group-local failure into
    visible report fallbacks here; cancellation remains cancellation.
    """
    try:
        subgraph = _build_analyst_subgraph(analyst_keys, ctx)
        result = await subgraph.ainvoke(state, config={"recursion_limit": recursion_limit})
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - this is the per-group resilience boundary
        logger.exception(
            "[market_intelligence] analyst group failed keys=%s; keeping other groups running.",
            analyst_keys,
        )
        return market_intelligence_failure_update(analyst_keys, exc)

    report_keys = _group_report_keys(analyst_keys) or _report_keys()
    return {report_key: result.get(report_key, "") for report_key in report_keys if report_key in result}


def _build_analyst_subgraph(enabled_keys: list[str], ctx: AgentRunContext):
    """
    Build & compile the analyst chain for *enabled_keys*.

    Mirrors the analyst section of the original GraphSetup, but terminates at
    END instead of handing off to the Synthesis Manager. Reuses each analyst's
    registered factory, its ToolNode, the auto-generated ConditionalLogic
    router and the message-clear node — so the analyst/tool behaviour is
    byte-for-byte the proven path.
    """
    sync_registry_to_graph()
    plan = build_analyst_execution_plan(
        enabled_keys,
        concurrency_limit=ctx.config.get("analyst_concurrency_limit", 1),
    )
    workflow = StateGraph(AgentState)

    for spec in plan.specs:
        _add_analyst_nodes(workflow, spec, ctx)

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


def create_market_intelligence_node(ctx: AgentRunContext) -> NodeFn:
    async def market_intelligence_node(state) -> dict:
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
            return await _run_analyst_subgraph(enabled, ctx, state, recursion_limit=recur)

        active_teams: dict[str, list[str]] = {}
        assigned: set[str] = set()
        for team_name, team_keys in ANALYST_TEAMS.items():
            team_enabled = [k for k in enabled if k in team_keys]
            if team_enabled:
                active_teams[team_name] = team_enabled
                assigned.update(team_enabled)

        leftover = [k for k in enabled if k not in assigned]
        if leftover:
            active_teams["extra"] = leftover

        semaphore = asyncio.Semaphore(concurrency)

        async def _run_team(team_keys: list[str]) -> dict:
            async with semaphore:
                analyst_state = {**state, "messages": list(state.get("messages", []))}
                return await _run_analyst_subgraph(team_keys, ctx, analyst_state, recursion_limit=recur)

        results = await asyncio.gather(*[_run_team(keys) for keys in active_teams.values()])
        merged: dict = {}
        for r in results:
            for report_key, report in r.items():
                # Teams now return disjoint key sets; never let a stray blank
                # win over a report another team already produced.
                if report or report_key not in merged:
                    merged[report_key] = report
        return merged

    return market_intelligence_node
