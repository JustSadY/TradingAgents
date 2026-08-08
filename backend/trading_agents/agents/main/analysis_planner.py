"""Pre-analysis, direction-neutral investigation planner.

The planner is intentionally upstream of every market analyst.  It receives a
sanitised strategy context containing only hypotheses, invalidation checks, and
open questions — never the previous Buy/Sell rating, conviction, or outcome.
That gives repeat analyses continuity without turning the analyst team into a
confirmation-bias machine.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import (
    AnalysisPlan,
    AnalysisPriority,
    InvalidationCondition,
    PriorAssumption,
    PriorityEvidence,
)
from backend.trading_agents.agents.utils.agent_utils import build_instrument_context, get_general_settings_block

logger = logging.getLogger(__name__)

MAIN_KEY = "analysis_planner"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _fallback_plan(state: dict) -> AnalysisPlan:
    ticker = str(state.get("company_of_interest") or "the instrument")
    context = _mapping(_mapping(state.get("strategy_context")).get("blind_planning_context"))
    assumptions = context.get("prior_assumptions") if isinstance(context.get("prior_assumptions"), list) else []
    questions = context.get("open_questions") if isinstance(context.get("open_questions"), list) else []
    invalidations: list[InvalidationCondition] = []
    for raw in context.get("invalidation_conditions") or []:
        try:
            invalidations.append(InvalidationCondition.model_validate(raw))
        except Exception:
            # Historical strategies can predate the strict invalidation schema.
            # They remain review prompts rather than causing the fresh run to
            # fail; the reconciler will tighten them on a material revision.
            continue

    analyst_questions = {
        "technical": ["Has the trend structure or volatility profile changed?"],
        "fundamental": ["Do operating performance and valuation evidence support the current assumptions?"],
        "macro_sentiment": ["Has the macro or sentiment environment changed in a way that affects the assumptions?"],
        "catalyst_options": ["Are upcoming catalysts or derivatives signals creating an unaddressed risk?"],
    }
    prior_assumptions: list[PriorAssumption] = []
    for index, raw_assumption in enumerate(assumptions[:8], start=1):
        statement = str(raw_assumption).strip()
        if not statement:
            continue
        try:
            prior_assumptions.append(
                PriorAssumption(
                    assumption_id=f"prior_assumption_{index}",
                    statement=statement,
                    test_method="Seek current, source-grounded evidence that could confirm or contradict this assumption.",
                    priority=AnalysisPriority.HIGH,
                )
            )
        except ValueError:
            # Older exact strategies can contain a directional sentence.  It
            # must not leak through the neutral planner just because it was
            # valid when originally persisted.
            logger.debug("Omitting non-neutral prior assumption from planner fallback")

    return AnalysisPlan(
        objective=f"Independently test the current evidence and open assumptions for {ticker}.",
        prior_assumptions_to_test=prior_assumptions,
        invalidations_to_check=invalidations,
        unresolved_questions=[str(item) for item in questions if str(item).strip()],
        analyst_questions=analyst_questions,
        priority_evidence=[
            PriorityEvidence(
                description="Recent source-grounded evidence that can confirm or challenge key assumptions.",
                source_family="market_data",
                priority=AnalysisPriority.HIGH,
            )
        ],
        expected_data_gaps=[],
        horizon="current analysis horizon",
        source_strategy_version=context.get("source_strategy_version"),
    )


def _render_plan(plan: AnalysisPlan) -> str:
    lines = ["## Analysis Plan", "", f"**Objective:** {plan.objective}", "", "**Priority analyst questions:**"]
    for analyst, questions in plan.analyst_questions.items():
        lines.append(f"- **{analyst}:** " + " ".join(questions))
    if plan.unresolved_questions:
        lines.extend(["", "**Open questions:**"])
        lines.extend(f"- {question}" for question in plan.unresolved_questions)
    if plan.invalidations_to_check:
        lines.extend(["", "**Invalidations to check:**"])
        lines.extend(f"- {item.statement}" for item in plan.invalidations_to_check)
    return "\n".join(lines)


def _set_plan_cache_key(plan: AnalysisPlan) -> None:
    """Expose the neutral plan fingerprint to cache helpers for this run."""

    from backend.trading_agents.agents.data.chart_tools import active_run_context

    context = active_run_context.get(None)
    if context is None:
        return
    serialized = json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    context["analysis_plan_cache_key"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def create_analysis_planner_node(ctx: AgentRunContext) -> NodeFn:
    async def analysis_planner_node(state: dict) -> dict:
        if not ctx.is_enabled(MAIN_KEY):
            plan = _fallback_plan(state)
            _set_plan_cache_key(plan)
            return {
                "analysis_plan_json": plan.model_dump(mode="json"),
                "analysis_plan_report": _render_plan(plan),
            }

        ticker = str(state.get("company_of_interest") or "")
        asset_type = str(state.get("asset_type") or "stock")
        blind_context = _mapping(_mapping(state.get("strategy_context")).get("blind_planning_context"))
        # The serialized context intentionally contains no strategic_bias,
        # accepted_rating, conviction, prior decision, or outcome values.
        context_json = json.dumps(blind_context, ensure_ascii=False, default=str)
        prompt = f"""You are an independent investment research planner. Build a neutral investigation
plan for {ticker}. Your job is to decide what should be tested, not to recommend
an action or validate a previous action.

{build_instrument_context(ticker, asset_type)}

## Blind prior-assumption context
{context_json}

Rules:
- Do not use Buy, Sell, Overweight, Underweight, position sizes, entry prices,
  stops, targets, or any executable recommendation.
- Treat prior assumptions as hypotheses that may fail. Include evidence that
  could disconfirm them as well as evidence that could support them.
- Assign neutral questions to technical, fundamental, macro_sentiment, and
  catalyst_options teams where relevant.
- Preserve a prior invalidation only when it can be stated as a testable
  condition; do not invent numerical thresholds.
- Return only an AnalysisPlan matching the supplied schema.
{get_general_settings_block()}"""
        fallback = _fallback_plan(state)
        try:
            result = await ainvoke_structured_or_freetext(
                bind_structured(ctx.llm_for(MAIN_KEY), AnalysisPlan, "Analysis Planner"),
                ctx.llm_for(MAIN_KEY),
                prompt,
                "Analysis Planner",
                schema=AnalysisPlan,
            )
            plan = result if isinstance(result, AnalysisPlan) else fallback
        except Exception as exc:  # noqa: BLE001 - neutral fallback is safer than an empty plan
            logger.warning("Analysis planner failed for %s: %s", ticker, exc)
            plan = fallback
        _set_plan_cache_key(plan)
        return {
            "analysis_plan_json": plan.model_dump(mode="json"),
            "analysis_plan_report": _render_plan(plan),
        }

    return analysis_planner_node


__all__ = ["create_analysis_planner_node"]
