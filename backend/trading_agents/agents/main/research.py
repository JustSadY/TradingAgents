"""
Main Agent: Research Manager.

Owns the research sub-agents and makes the branch's own call (the investment
plan). Orchestration order:

    Synthesis Manager (sub)  →  Bull ⇄ Bear debate (subs)
                             →  Auditor (sub)
                             →  Research Manager judgement (this main agent)

The debate loop is run imperatively here, replicating the old
``ConditionalLogic.should_continue_debate`` routing (alternate speakers, stop
at ``2 × max_debate_rounds``) instead of LangGraph conditional edges.

Kill-switch behaviour:
  • research_manager disabled  → emit a neutral investment plan and skip every
    sub-agent (zero tokens).
  • a single sub disabled      → that step is skipped; the rest proceed.
"""

from __future__ import annotations

import inspect
import logging

from backend.trading_agents.agents.base import (
    AgentRunContext,
    NodeFn,
    neutral_invest_debate_state,
)
from backend.trading_agents.agents.sub.managers.auditor_node import create_auditor_node
from backend.trading_agents.agents.sub.managers.research_manager import create_research_manager
from backend.trading_agents.agents.sub.managers.synthesis_manager import create_synthesis_manager
from backend.trading_agents.agents.sub.researchers.bear_researcher import create_bear_researcher
from backend.trading_agents.agents.sub.researchers.bull_researcher import create_bull_researcher

logger = logging.getLogger(__name__)

MAIN_KEY = "research_manager"


async def _safe(label: str, fn, state: dict, fallback: dict) -> dict:
    try:
        if inspect.iscoroutinefunction(fn):
            return await fn(state)
        return fn(state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[research_manager] sub '%s' failed: %s — using fallback.", label, exc, exc_info=True)
        return fallback


def create_research_manager_node(ctx: AgentRunContext) -> NodeFn:
    async def research_manager_node(state) -> dict:
        # Tier-1 kill-switch.
        if not ctx.is_enabled(MAIN_KEY):
            logger.info("[research_manager] branch disabled — skipping research.")
            return {
                "synthesis_report": "",
                "audit_report": "",
                "investment_debate_state": neutral_invest_debate_state(""),
                "investment_plan": "",
            }

        local = dict(state)
        out: dict = {}

        def apply(update: dict) -> None:
            out.update(update)
            local.update(update)

        # ---- Synthesis Manager (sub) ----
        if ctx.is_enabled("synthesis_manager"):
            node = create_synthesis_manager(ctx.llm_for("synthesis_manager"))
            apply(await _safe("synthesis_manager", node, local, {"synthesis_report": ""}))
        else:
            apply({"synthesis_report": ""})

        # ---- Bull ⇄ Bear debate (subs) ----
        bull_on = ctx.is_enabled("bull_researcher")
        bear_on = ctx.is_enabled("bear_researcher")
        if bull_on and bear_on:
            bull = create_bull_researcher(ctx.llm_for("bull_researcher"))
            bear = create_bear_researcher(ctx.llm_for("bear_researcher"))
            max_rounds = ctx.config.get("max_debate_rounds", 1)
            # Ensure a debate state exists to read counts from.
            if not local.get("investment_debate_state"):
                apply({"investment_debate_state": neutral_invest_debate_state()})

            guard = 0
            while local["investment_debate_state"]["count"] < 2 * max_rounds and guard < 50:
                guard += 1
                current = local["investment_debate_state"].get("current_response", "")
                speaker = bear if current.startswith("Bull") else bull
                label = "bear_researcher" if current.startswith("Bull") else "bull_researcher"
                fb = {
                    "investment_debate_state": {
                        **local["investment_debate_state"],
                        "count": local["investment_debate_state"]["count"] + 1,
                        "current_response": f"({label} unavailable.)",
                    }
                }
                apply(await _safe(label, speaker, local, fb))
        else:
            logger.info("[research_manager] debate skipped (bull=%s bear=%s).", bull_on, bear_on)
            if not local.get("investment_debate_state"):
                apply({"investment_debate_state": neutral_invest_debate_state()})

        # ---- Auditor (sub) ----
        if ctx.is_enabled("auditor"):
            node = create_auditor_node(ctx.llm_for("auditor"))
            apply(await _safe("auditor", node, local, {"audit_report": ""}))
        else:
            apply({"audit_report": ""})

        # ---- Research Manager judgement (this main agent's own decision) ----
        judge = create_research_manager(ctx.llm_for("research_manager"))
        apply(
            await _safe(
                "research_manager",
                judge,
                local,
                {
                    "investment_plan": "Research manager unavailable; proceeding with available reports.",
                },
            )
        )

        return out

    return research_manager_node
