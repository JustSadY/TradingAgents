"""
Main Agent: Research Manager.

Owns the research sub-agents and makes the branch's own call (the investment
plan). Orchestration order:

    Synthesis Manager (sub)  →  Bull ⇄ Bear debate (subs)
                             →  Auditor (sub)
                             →  Research Manager judgement (this main agent)

The debate loop is run imperatively here, replicating the old
``ConditionalLogic.should_continue_debate`` routing (alternate speakers, stop
at ``2 × max_debate_rounds``) instead of LangGraph conditional edges. Because
an imperative loop is invisible to LangGraph streaming until this whole node
returns, each completed turn is also published through the current run's live
debate bridge.

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
from backend.trading_agents.agents.runtime.debate_stream import emit_live_debate_state
from backend.trading_agents.agents.runtime.resilience import classify_error, record_agent_result
from backend.trading_agents.agents.sub.managers.auditor_node import create_auditor_node
from backend.trading_agents.agents.sub.managers.research_manager import create_research_manager
from backend.trading_agents.agents.sub.managers.synthesis_manager import create_synthesis_manager
from backend.trading_agents.agents.sub.researchers.bear_researcher import create_bear_researcher
from backend.trading_agents.agents.sub.researchers.bull_researcher import create_bull_researcher

logger = logging.getLogger(__name__)

MAIN_KEY = "research_manager"


async def _report_sub_failure(label: str, exc: Exception) -> None:
    """Make an imperative sub-agent failure visible to run health + live UI.

    The Research Manager intentionally keeps useful synthesis/debate/audit
    output when one inner step fails. That graceful degradation must not hide
    the exception from the report card merely because the outer LangGraph node
    itself returned successfully.
    """
    error = str(exc) or exc.__class__.__name__
    record_agent_result(label, fallback=True, error=error)
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        run_ctx = active_run_context.get(None) or {}
        emitter = run_ctx.get("emitter")
        if emitter is None:
            return
        error_type = classify_error(exc)
        await emitter.emit_node_error(label, "subagent", error[:500], error_type)
        await emitter.emit_fallback(label, "subagent", error[:500])
    except Exception:
        logger.debug("[research_manager] could not emit failure telemetry for %s", label, exc_info=True)


async def _safe(label: str, fn, state: dict, fallback: dict) -> dict:
    try:
        if inspect.iscoroutinefunction(fn):
            return await fn(state)
        return fn(state)
    except Exception as exc:
        logger.warning("[research_manager] sub '%s' failed: %s — using fallback.", label, exc, exc_info=True)
        await _report_sub_failure(label, exc)
        return fallback


def _debate_count(state: dict) -> int:
    try:
        return max(0, int(state.get("count", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _append_history(history: object, argument: str) -> str:
    existing = str(history or "").strip()
    return f"{existing}\n{argument}".strip() if existing else argument


def _fallback_debate_update(label: str, debate_state: dict) -> dict:
    """Create a canonical failed turn without breaking Bull/Bear alternation."""

    side = "bear" if label == "bear_researcher" else "bull"
    other = "bull" if side == "bear" else "bear"
    sender = "Bear Analyst" if side == "bear" else "Bull Analyst"
    argument = f"{sender}: This debate turn was unavailable; the panel will continue with the remaining evidence."
    return {
        "investment_debate_state": {
            "history": _append_history(debate_state.get("history"), argument),
            f"{side}_history": _append_history(debate_state.get(f"{side}_history"), argument),
            f"{other}_history": str(debate_state.get(f"{other}_history", "") or ""),
            "current_response": argument,
            "judge_decision": str(debate_state.get("judge_decision", "") or ""),
            "count": _debate_count(debate_state) + 1,
        }
    }


def _research_judgement_fallback(state: dict) -> dict:
    """Preserve completed research artifacts while failing the final judge closed."""
    plan = (
        "Research judgement unavailable; the run is degraded. Research posture: Neutral. "
        "Portfolio Manager must rely on the available analyst reports, synthesis, audit, and debate evidence "
        "without treating this fallback as a directional research conclusion."
    )
    debate = dict(state.get("investment_debate_state") or neutral_invest_debate_state())
    debate["judge_decision"] = plan
    debate["current_response"] = plan
    debate["count"] = _debate_count(debate)
    return {
        "investment_debate_state": debate,
        "investment_plan": plan,
    }


def create_research_manager_node(ctx: AgentRunContext) -> NodeFn:
    async def research_manager_node(state) -> dict:
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

        if ctx.is_enabled("synthesis_manager"):
            node = create_synthesis_manager(ctx.llm_for("synthesis_manager"))
            apply(await _safe("synthesis_manager", node, local, {"synthesis_report": ""}))
        else:
            apply({"synthesis_report": ""})

        bull_on = ctx.is_enabled("bull_researcher")
        bear_on = ctx.is_enabled("bear_researcher")
        if bull_on and bear_on:
            bull = create_bull_researcher(ctx.llm_for("bull_researcher"))
            bear = create_bear_researcher(ctx.llm_for("bear_researcher"))
            try:
                max_rounds = max(1, int(ctx.config.get("max_debate_rounds", 1) or 1))
            except (TypeError, ValueError):
                max_rounds = 1
            if not local.get("investment_debate_state"):
                apply({"investment_debate_state": neutral_invest_debate_state()})

            guard = 0
            while _debate_count(local["investment_debate_state"]) < 2 * max_rounds and guard < 50:
                guard += 1
                current = str(local["investment_debate_state"].get("current_response", "") or "")
                previous_was_bull = current.lstrip().lower().startswith("bull")
                speaker = bear if previous_was_bull else bull
                label = "bear_researcher" if previous_was_bull else "bull_researcher"
                fallback = _fallback_debate_update(label, local["investment_debate_state"])
                apply(await _safe(label, speaker, local, fallback))

                # LangGraph cannot expose intermediate state from this
                # imperative sub-loop. Emit the completed turn immediately;
                # the outer observer will see the same count later and dedupe.
                await emit_live_debate_state("investment", local.get("investment_debate_state"))
        else:
            logger.info("[research_manager] debate skipped (bull=%s bear=%s).", bull_on, bear_on)
            if not local.get("investment_debate_state"):
                apply({"investment_debate_state": neutral_invest_debate_state()})

        if ctx.is_enabled("auditor"):
            node = create_auditor_node(ctx.llm_for("auditor"))
            apply(await _safe("auditor", node, local, {"audit_report": ""}))
        else:
            apply({"audit_report": ""})

        fallback = _research_judgement_fallback(local)
        try:
            judge = create_research_manager(ctx.llm_for("research_manager"))
        except Exception as exc:
            logger.warning("[research_manager] final judge factory failed: %s — using fallback.", exc, exc_info=True)
            await _report_sub_failure("research_manager", exc)
            apply(fallback)
            return out

        apply(await _safe("research_manager", judge, local, fallback))
        return out

    return research_manager_node
