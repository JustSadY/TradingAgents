"""Graph adapter for deterministic decision stability and optional verification."""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Mapping
from typing import Any

from backend.services.confidence_calibration_service import calibrate_confidence
from backend.services.decision_stability_service import StabilityThresholds, evaluate_decision_stability
from backend.trading_agents.agents.base import AgentRunContext, NodeFn
from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext, bind_structured
from backend.trading_agents.agents.schemas import (
    AcceptedDecision,
    DataQualityAssessment,
    DataQualityLevel,
    DecisionTransition,
    DecisionTransitionOutcome,
    EvidenceGroup,
    EvidenceStrength,
    ExecutionAction,
    PMDecisionProposal,
    PortfolioDecision,
    PortfolioRating,
    ReversalVerdict,
    ReversalVerification,
    StrategicState,
    TacticalAction,
)

logger = logging.getLogger(__name__)

MAIN_KEY = "decision_stability_controller"
_STRENGTH_VALUES = {"none": 0.0, "weak": 0.3, "moderate": 0.6, "strong": 0.9}


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return copy.deepcopy(parsed) if isinstance(parsed, dict) else {}
    return {}


def _proposal_from_state(state: Mapping[str, Any]) -> PMDecisionProposal | None:
    raw = _mapping(state.get("pm_proposal_json"))
    if not raw:
        raw = _mapping(state.get("portfolio_decision_json"))
    if "proposed_decision" not in raw:
        raw = {
            "proposed_decision": raw,
            "rationale": "Portfolio Manager proposal without additional structured rationale.",
            "supporting_evidence_ids": [],
            "triggered_invalidation_ids": [],
        }
    try:
        return PMDecisionProposal.model_validate(raw)
    except Exception as exc:
        logger.warning("Portfolio proposal could not be parsed for stability controller: %s", exc)
        return None


def _fallback_hold_proposal() -> PMDecisionProposal:
    return PMDecisionProposal(
        proposed_decision=PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="No executable proposal was available.",
            investment_thesis="The decision controller received no valid Portfolio Manager proposal.",
            confidence_score=0.0,
            suggested_capital=0.0,
        ),
        rationale="Invalid or missing Portfolio Manager proposal.",
    )


def _quality_from_state(state: Mapping[str, Any], selected_analysts: list[str]) -> DataQualityAssessment:
    synthesis = _mapping(state.get("synthesis_json"))
    source = _mapping(synthesis.get("data_quality"))
    try:
        source_quality = DataQualityAssessment.model_validate(source)
    except Exception:
        source_quality = None
    try:
        from backend.services.analysis.run_quality import assess_run_quality

        report_quality = assess_run_quality(state, selected_analysts, state.get("final_trade_decision"))
        report_score = float(report_quality.get("score", 0.0))
    except Exception:
        report_score = 0.0
    if source_quality is not None:
        # A very complete text run with only one evidence domain should not be
        # treated as a high-quality reversal, and vice versa.  The lower score
        # is a conservative shared gate.
        score = min(source_quality.score, report_score) if report_score else source_quality.score
        available = source_quality.available_evidence_groups
        unavailable = source_quality.unavailable_evidence_groups
        gaps = source_quality.known_gaps
    else:
        score = report_score
        available = []
        unavailable = []
        gaps = ["Structured synthesis data quality was unavailable."]
    level = DataQualityLevel.HIGH if score >= 75 else DataQualityLevel.MEDIUM if score >= 50 else DataQualityLevel.LOW
    return DataQualityAssessment(
        level=level,
        score=max(0.0, min(100.0, score)),
        available_evidence_groups=available,
        unavailable_evidence_groups=unavailable,
        known_gaps=gaps,
    )


def _evidence_for_controller(state: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    synthesis = _mapping(state.get("synthesis_json"))
    groups = synthesis.get("evidence_groups")
    if not isinstance(groups, Mapping):
        return {}, []
    compact: dict[str, dict[str, Any]] = {}
    flattened: list[dict[str, Any]] = []
    for raw_group, raw_items in groups.items():
        group = str(raw_group)
        if not isinstance(raw_items, list):
            continue
        items = [_mapping(item) for item in raw_items if _mapping(item)]
        if not items:
            continue
        flattened.extend(items)
        # Preserve one strongest independently usable source per evidence
        # group.  The pure controller separately deduplicates source families.
        def strength(item: dict[str, Any]) -> float:
            raw = item.get("evidence_strength", item.get("strength", "none"))
            return _STRENGTH_VALUES.get(str(raw).lower(), 0.0)

        representative = max(items, key=strength)
        compact[group] = {
            "bias": representative.get("bias", "Neutral"),
            "evidence_strength": strength(representative),
            "source_family": representative.get("source_family", group),
            "independent": bool(representative.get("independent_for_reversal", group != EvidenceGroup.REVIEW.value)),
        }
    return compact, flattened


def _invalidation_items(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    synthesis = _mapping(state.get("synthesis_json"))
    raw = synthesis.get("triggered_invalidations")
    return [_mapping(item) for item in raw] if isinstance(raw, list) else []


def _hard_risk_from_state(
    state: Mapping[str, Any],
    invalidations: list[dict[str, Any]],
) -> object:
    """Return an explicit emergency input for the deterministic controller.

    A caller may still supply a stop/drawdown/portfolio breach through the
    reserved ``hard_risk_exit`` state field.  Independently, a *structured,
    explicitly triggered critical* thesis invalidation has unambiguous
    emergency semantics: it must be allowed to reduce or exit risk even while
    stability enforcement is in shadow/off mode.  Ordinary material/watch
    invalidations remain subject to normal hysteresis.
    """

    explicit = state.get("hard_risk_exit")
    if explicit:
        return explicit

    critical_ids = [
        str(item.get("condition_id") or item.get("id") or "critical_invalidation")
        for item in invalidations
        if str(item.get("severity") or "").strip().lower() == "critical"
    ]
    if not critical_ids:
        return None
    return {
        "triggered": True,
        "reason_code": "critical_thesis_invalidation",
        "invalidation_condition_ids": critical_ids,
    }


def _thresholds(ctx: AgentRunContext) -> StabilityThresholds:
    config = ctx.config
    min_confidence = max(0.0, min(1.0, float(config.get("decision_stability_min_confidence", 0.65) or 0.65)))
    min_quality = max(0.0, min(1.0, float(config.get("decision_stability_min_quality", 70) or 70) / 100.0))
    base = StabilityThresholds()
    return StabilityThresholds(
        initial_confidence=max(base.initial_confidence, min_confidence),
        initial_quality=max(base.initial_quality, min_quality),
        same_confidence=max(base.same_confidence, min_confidence),
        same_quality=max(base.same_quality, min_quality),
        reduce_one_step_confidence=max(base.reduce_one_step_confidence, min_confidence),
        reduce_one_step_quality=max(base.reduce_one_step_quality, min_quality),
        reduce_material_confidence=max(base.reduce_material_confidence, min_confidence),
        reduce_material_quality=max(base.reduce_material_quality, min_quality),
        increase_one_step_confidence=max(base.increase_one_step_confidence, min_confidence),
        increase_one_step_quality=max(base.increase_one_step_quality, min_quality),
        reversal_confidence=max(base.reversal_confidence, min_confidence),
        reversal_quality=max(base.reversal_quality, min_quality),
        high_quality=max(base.high_quality, min_quality),
        min_independent_groups_for_reversal=max(
            base.min_independent_groups_for_reversal,
            int(config.get("decision_stability_min_evidence_groups", 2) or 2),
        ),
        min_evidence_strength=base.min_evidence_strength,
        material_allocation_relative_change=base.material_allocation_relative_change,
    )


def _strategic_state(state: Mapping[str, Any]) -> StrategicState:
    candidate = _mapping(state.get("strategy_candidate_json"))
    after = _mapping(candidate.get("strategy_after"))
    action = str(candidate.get("revision_action") or "").upper()
    status = str(after.get("status") or "").upper()
    if action == "INVALIDATE" or status in {"INVALIDATED", "CLOSED"}:
        return StrategicState.INVALIDATED
    bias = str(after.get("strategic_bias") or "Neutral").lower()
    if bias == "bullish":
        return StrategicState.BULLISH_WEAKENING if action == "WEAKEN" else StrategicState.BULLISH
    if bias == "bearish":
        return StrategicState.BEARISH_WEAKENING if action == "WEAKEN" else StrategicState.BEARISH
    return StrategicState.NEUTRAL


def _tactical_action(rating: PortfolioRating, execution_action: str) -> TacticalAction:
    if execution_action == "reduce_only":
        if rating in {PortfolioRating.BUY, PortfolioRating.OVERWEIGHT}:
            # A Buy-shaped order can be risk reducing only when it covers an
            # existing short.  Keep that distinction explicit so the accepted
            # decision never mislabels a forced cover as new long exposure.
            return TacticalAction.COVER_SHORT
        if rating is PortfolioRating.SELL:
            return TacticalAction.EXIT
        return TacticalAction.REDUCE_EXPOSURE
    if rating in {PortfolioRating.BUY, PortfolioRating.OVERWEIGHT}:
        return TacticalAction.INCREASE_EXPOSURE
    if rating is PortfolioRating.UNDERWEIGHT:
        return TacticalAction.REDUCE_EXPOSURE
    if rating is PortfolioRating.SELL:
        return TacticalAction.EXIT
    return TacticalAction.HOLD


def _execution_action(raw: str) -> ExecutionAction:
    if raw == "reduce_only":
        return ExecutionAction.REDUCE_ONLY
    if raw == "order":
        return ExecutionAction.PLACE_ORDER
    return ExecutionAction.NO_NEW_ORDER


async def _verify_major_reversal(
    ctx: AgentRunContext,
    *,
    evaluation: Mapping[str, Any],
    evidence: list[dict[str, Any]],
    invalidations: list[dict[str, Any]],
) -> ReversalVerification | None:
    transition = _mapping(evaluation.get("transition"))
    if not transition.get("is_cross_zero_reversal") or not evaluation.get("proposal_accepted"):
        return None
    if not ctx.config.get("reversal_verifier_enabled", True):
        return ReversalVerification(
            verdict=ReversalVerdict.INSUFFICIENT_EVIDENCE,
            rationale="Major reversal verifier is disabled; enforcement cannot approve this reversal.",
        )
    prompt = f"""You are a narrow reversal verifier. Do not make a new investment decision.
Determine whether this major rating reversal has at least two independent evidence groups
and an explicit thesis invalidation.

Previous accepted decision: {_mapping(evaluation.get('previous_accepted_decision'))}
Raw PM proposal: {_mapping(evaluation.get('pm_proposal'))}
Independent evidence summary: {evidence}
Triggered invalidations: {invalidations}

Return only a ReversalVerification. APPROVE only when the evidence explicitly
justifies abandoning the prior strategy."""
    try:
        result = await ainvoke_structured_or_freetext(
            bind_structured(ctx.llm_for("strategy_reconciler"), ReversalVerification, "Reversal Verifier"),
            ctx.llm_for("strategy_reconciler"),
            prompt,
            "Reversal Verifier",
            schema=ReversalVerification,
        )
        if isinstance(result, ReversalVerification):
            return result
    except Exception as exc:  # noqa: BLE001 - major reversal must fail closed
        logger.warning("Reversal verification unavailable: %s", exc)
    return ReversalVerification(
        verdict=ReversalVerdict.INSUFFICIENT_EVIDENCE,
        rationale="The optional major-reversal verifier did not return valid independent confirmation.",
    )


def _force_verifier_rejection(evaluation: dict[str, Any], verification: ReversalVerification) -> dict[str, Any]:
    if verification.verdict is ReversalVerdict.APPROVE:
        return evaluation
    proposal = _mapping(evaluation.get("pm_proposal"))
    held = copy.deepcopy(proposal)
    held.update(
        {
            "rating": "Hold",
            "entry_price": None,
            "stop_loss": None,
            "take_profit_price": None,
            "position_size_pct": None,
            "suggested_capital": 0.0,
            "execution_action": "no_order",
        }
    )
    codes = list(evaluation.get("reason_codes") or [])
    codes.append("reversal_verifier_not_approved")
    evaluation.update(
        {
            "status": "rejected",
            "proposal_accepted": False,
            "accepted": False,
            "accepted_decision": held,
            "execution_action": "no_order",
            "reduce_only": False,
            "reason_codes": list(dict.fromkeys(codes)),
        }
    )
    return evaluation


def _transition_model(
    *,
    proposal: PMDecisionProposal,
    previous: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any],
    quality: DataQualityAssessment,
    strategic_state: StrategicState,
    verification: ReversalVerification | None,
) -> DecisionTransition:
    accepted_raw = _mapping(evaluation.get("accepted_decision"))
    confidence = float(evaluation.get("calibrated_confidence", proposal.proposed_decision.confidence_score) or 0.0)
    accepted_raw["confidence_score"] = confidence
    accepted = PortfolioDecision.model_validate(accepted_raw)
    execution = _execution_action(str(evaluation.get("execution_action") or "no_order"))
    tactical = _tactical_action(accepted.rating, str(evaluation.get("execution_action") or "no_order"))
    accepted_decision = AcceptedDecision(
        decision=accepted,
        calibrated_confidence=confidence,
        strategic_state=strategic_state,
        tactical_action=tactical,
        execution_action=execution,
    )
    previous_model = None
    if previous:
        try:
            previous_model = PortfolioDecision.model_validate(previous)
        except Exception:
            previous_model = None
    if str(evaluation.get("status")) == "hard_risk_exit":
        outcome = DecisionTransitionOutcome.EMERGENCY_RISK_EXIT
    elif not evaluation.get("proposal_accepted") and proposal.proposed_decision.rating is not accepted.rating:
        outcome = DecisionTransitionOutcome.BLOCKED_CHANGE
    elif previous_model is None:
        outcome = DecisionTransitionOutcome.INITIAL_ACCEPTED
    elif proposal.proposed_decision.rating is previous_model.rating:
        outcome = DecisionTransitionOutcome.UNCHANGED
    else:
        outcome = DecisionTransitionOutcome.ACCEPTED_CHANGE
    strength = EvidenceStrength.NONE
    for value in _mapping(evaluation.get("evidence")).get("independent_supporting_groups", []):
        if value:
            strength = EvidenceStrength.STRONG
            break
    return DecisionTransition(
        previous_accepted_decision=previous_model,
        pm_proposal=proposal,
        accepted_decision=accepted_decision,
        outcome=outcome,
        reason="; ".join(str(item) for item in (evaluation.get("reason_codes") or [])) or "controller_evaluated",
        evidence_strength=strength,
        run_quality=quality,
        reversal_verification=verification,
    )


def create_decision_stability_controller_node(ctx: AgentRunContext) -> NodeFn:
    async def decision_stability_controller_node(state: dict) -> dict:
        proposal = _proposal_from_state(state) or _fallback_hold_proposal()
        context = _mapping(state.get("strategy_context"))
        quality = _quality_from_state(state, ctx.selected_analysts)
        controller_enabled = ctx.is_enabled(MAIN_KEY)
        mode = str(ctx.config.get("decision_stability_mode", "shadow") or "shadow").lower()
        # The catalog switch must remain a true kill-switch.  Retain a
        # deterministic counterfactual for auditability, but spend no verifier
        # tokens and never enforce a non-emergency change while it is off.
        if not controller_enabled:
            mode = "off"
        calibration = calibrate_confidence(
            proposal.proposed_decision.confidence_score,
            proposal.proposed_decision.rating.value,
            ctx.config.get("confidence_calibration_context")
            if ctx.config.get("confidence_calibration_enabled", False)
            else None,
        )
        evidence_groups, evidence = _evidence_for_controller(state)
        invalidations = _invalidation_items(state)
        hard_risk = _hard_risk_from_state(state, invalidations)
        candidate = _mapping(state.get("strategy_candidate_json"))
        evaluation = evaluate_decision_stability(
            proposal.proposed_decision.model_dump(mode="json"),
            context.get("previous_accepted_decision"),
            candidate.get("revision_action"),
            quality.model_dump(mode="json"),
            calibration["calibrated_confidence"],
            evidence_groups,
            invalidations,
            hard_risk,
            thresholds=_thresholds(ctx),
        )
        verification = None
        if mode != "off":
            verification = await _verify_major_reversal(
                ctx,
                evaluation=evaluation,
                evidence=evidence,
                invalidations=invalidations,
            )
        if verification is not None:
            evaluation = _force_verifier_rejection(dict(evaluation), verification)

        transition = _transition_model(
            proposal=proposal,
            previous=_mapping(context.get("previous_accepted_decision")) or None,
            evaluation=evaluation,
            quality=quality,
            strategic_state=_strategic_state(state),
            verification=verification,
        )
        proposed_json = proposal.proposed_decision.model_dump(mode="json")
        controller_json = transition.accepted_decision.decision.model_dump(mode="json")
        controller_json["execution_action"] = transition.accepted_decision.execution_action.value.lower()
        controller_json["tactical_action"] = transition.accepted_decision.tactical_action.value.lower()
        # Shadow keeps historical PM execution semantics intact but stores the
        # controller's counterfactual in the transition.  Hard safety exits are
        # intentionally never shadowed.
        enforce = (controller_enabled and mode == "enforce") or str(evaluation.get("status")) == "hard_risk_exit"
        canonical = controller_json if enforce else proposed_json
        canonical_text = transition.accepted_decision.decision if enforce else proposal.proposed_decision
        from backend.trading_agents.agents.schemas import render_pm_decision

        transition_json = transition.model_dump(mode="json")
        transition_json["mode"] = mode
        transition_json["controller_status"] = evaluation.get("status")
        transition_json["controller_reason_codes"] = evaluation.get("reason_codes") or []
        transition_json["would_execution_action"] = evaluation.get("would_execution_action")
        transition_json["canonical_enforced"] = enforce
        return {
            "pm_proposal_json": proposal.model_dump(mode="json"),
            "portfolio_decision_json": canonical,
            "decision_transition_json": transition_json,
            "calibrated_confidence": calibration["calibrated_confidence"],
            "final_signal": canonical.get("rating", "Hold"),
            "final_trade_decision": render_pm_decision(canonical_text),
        }

    return decision_stability_controller_node


__all__ = ["create_decision_stability_controller_node"]
