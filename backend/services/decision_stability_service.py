"""Pure, deterministic guardrail for Portfolio Manager decision changes.

The controller deliberately has no database, graph, or LLM dependency. It
accepts plain mappings and returns a plain mapping so an orchestrator can run
it in shadow mode before it becomes the canonical decision authority.

``pm_proposal`` is always preserved verbatim in the result. The separately
returned ``accepted_decision`` is the only payload a caller should persist or
send to execution. A rejected proposal becomes a tactical ``Hold`` with
``no_order``; it does *not* replay the previous Buy/Sell as a fresh order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
from typing import Any

RATING_SCORES: dict[str, int] = {
    "Buy": 2,
    "Overweight": 1,
    "Hold": 0,
    "Underweight": -1,
    "Sell": -2,
}
"""Canonical five-tier ordinal ratings; never treat these as signed exposure."""

_RATING_ALIASES = {
    "buy": "Buy",
    "overweight": "Overweight",
    "hold": "Hold",
    "underweight": "Underweight",
    "sell": "Sell",
    "strong buy": "Buy",
    "strong_buy": "Buy",
    "strong sell": "Sell",
    "strong_sell": "Sell",
    "neutral": "Hold",
}
_ALLOCATION_KEYS = (
    "target_allocation_pct",
    "target_allocation",
    "target_weight",
    "position_size_pct",
    "allocation_pct",
    "target_exposure",
)
_NON_INDEPENDENT_GROUPS = frozenset({"review", "review_analyst", "audit", "auditor", "hindsight"})
_RISK_INCREASING_ACTIONS_BLOCKED = frozenset({"WEAKEN", "INVALIDATE"})
_RATING_RISK_MAGNITUDE = {
    "Buy": 2,
    "Overweight": 1,
    "Hold": 0,
    # Underweight means a smaller long target in the execution contract unless
    # a negative signed target explicitly says otherwise.
    "Underweight": 0,
    # Sell with target 0 is an exit/avoid recommendation, not a short. A short
    # requires a negative signed target exposure.
    "Sell": 0,
}


@dataclass(frozen=True)
class StabilityThresholds:
    """Default thresholds for confidence and analysis quality (all 0..1).

    The defaults intentionally make risk increases harder than risk reductions.
    A true cross-zero exposure reversal needs explicit invalidation evidence and
    independent support.
    """

    initial_confidence: float = 0.50
    initial_quality: float = 0.50
    same_confidence: float = 0.45
    same_quality: float = 0.45
    reduce_one_step_confidence: float = 0.50
    reduce_one_step_quality: float = 0.45
    reduce_material_confidence: float = 0.60
    reduce_material_quality: float = 0.55
    increase_one_step_confidence: float = 0.65
    increase_one_step_quality: float = 0.55
    increase_material_confidence: float = 0.75
    increase_material_quality: float = 0.65
    reversal_confidence: float = 0.82
    reversal_quality: float = 0.75
    high_quality: float = 0.75
    min_independent_groups_for_reversal: int = 2
    min_evidence_strength: float = 0.50
    material_allocation_relative_change: float = 0.50


@dataclass(frozen=True)
class _DecisionPoint:
    payload: dict[str, Any]
    rating: str | None
    score: int | None
    allocation: float | None
    allocation_key: str | None


def evaluate_decision_stability(
    proposal: Mapping[str, Any] | None = None,
    previous_accepted_decision: Mapping[str, Any] | None = None,
    candidate_strategy_action: str | Mapping[str, Any] | None = None,
    run_quality: Any = None,
    calibrated_confidence: Any = None,
    evidence_groups: Mapping[str, Any] | Sequence[Any] | None = None,
    triggered_invalidations: Any = None,
    hard_risk: Any = None,
    *,
    pm_proposal: Mapping[str, Any] | None = None,
    strategy_action: str | Mapping[str, Any] | None = None,
    quality: Any = None,
    invalidations: Any = None,
    hard_risk_exit: Any = None,
    thresholds: StabilityThresholds | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a Portfolio Manager proposal without performing any I/O.

    Target allocation/exposure is signed: positive is long, zero is flat, and
    negative is short. Rating labels remain descriptive tiers and never by
    themselves imply a short position. This avoids treating an Underweight
    reduction of a long as a long-to-short reversal.
    """
    if proposal is None:
        proposal = pm_proposal
    if candidate_strategy_action is None:
        candidate_strategy_action = strategy_action
    if run_quality is None:
        run_quality = quality
    if triggered_invalidations is None:
        triggered_invalidations = invalidations
    if hard_risk is None:
        hard_risk = hard_risk_exit

    config = _coerce_thresholds(thresholds)
    raw_proposal = deepcopy(dict(proposal)) if isinstance(proposal, Mapping) else {}
    previous_payload = _unwrap_previous(previous_accepted_decision)
    proposal_point = _decision_point(raw_proposal)
    previous_point = _decision_point(previous_payload)
    strategy_action = _strategy_action(candidate_strategy_action)
    quality_score, quality_label = _score_quality(run_quality)
    confidence_score, confidence_source, confidence_valid = _score_confidence(
        calibrated_confidence,
        raw_proposal,
    )
    evidence = _independent_supporting_groups(
        evidence_groups,
        proposal_score=proposal_point.score,
        config=config,
    )
    invalidation_triggered = _has_triggered_invalidation(triggered_invalidations)
    hard_risk_active, hard_risk_payload = _hard_risk_details(hard_risk)

    transition = _transition(previous_point, proposal_point, config)
    base = {
        "pm_proposal": raw_proposal,
        "previous_accepted_decision": previous_payload or None,
        "candidate_strategy_action": strategy_action,
        "calibrated_confidence": confidence_score,
        "confidence_source": confidence_source,
        "run_quality": {"score": quality_score, "label": quality_label},
        "evidence": evidence,
        "triggered_invalidation": invalidation_triggered,
        "transition": transition,
        "thresholds": asdict(config),
    }

    if proposal_point.rating is None:
        return _with_shadow_fields(
            _rejected_result(
                base,
                proposal_point,
                reasons=["invalid_proposal_rating"],
                required_confidence=None,
                required_quality=None,
            )
        )

    if hard_risk_active:
        accepted = _forced_reduce_only_decision(
            proposal_point,
            previous_point,
            hard_risk_payload,
        )
        return _with_shadow_fields(
            {
                **base,
                "status": "hard_risk_exit",
                "proposal_accepted": False,
                "accepted": False,
                "accepted_decision": accepted,
                "execution_action": "reduce_only",
                "reduce_only": True,
                "reason_codes": _hard_risk_reason_codes(hard_risk_payload),
                "required_confidence": None,
                "required_quality": None,
                "transition": {**transition, "accepted_rating": accepted["rating"]},
            }
        )

    required_confidence, required_quality = _required_thresholds(transition, config)
    reasons: list[str] = []
    if not confidence_valid:
        reasons.append("invalid_calibrated_confidence")
    elif confidence_score < required_confidence:
        reasons.append("confidence_below_threshold")
    if quality_score < required_quality:
        reasons.append("run_quality_below_threshold")

    if transition["is_cross_zero_reversal"]:
        if not invalidation_triggered:
            reasons.append("reversal_invalidation_missing")
        if evidence["independent_supporting_group_count"] < config.min_independent_groups_for_reversal:
            reasons.append("independent_evidence_missing")
        if quality_score < config.high_quality:
            reasons.append("major_reversal_requires_high_quality")

    if (
        previous_point.rating is not None
        and transition["movement"] == "risk_increase"
        and strategy_action in _RISK_INCREASING_ACTIONS_BLOCKED
    ):
        reasons.append("strategy_action_blocks_risk_increase")

    if reasons:
        return _with_shadow_fields(
            _rejected_result(
                base,
                proposal_point,
                reasons=_unique(reasons),
                required_confidence=required_confidence,
                required_quality=required_quality,
            )
        )

    accepted = _accepted_proposal(proposal_point, confidence_score)
    execution_action = "no_order" if accepted["rating"] == "Hold" else "order"
    return _with_shadow_fields(
        {
            **base,
            "status": "accepted",
            "proposal_accepted": True,
            "accepted": True,
            "accepted_decision": accepted,
            "execution_action": execution_action,
            "reduce_only": False,
            "reason_codes": ["proposal_meets_stability_requirements"],
            "required_confidence": required_confidence,
            "required_quality": required_quality,
            "transition": {**transition, "accepted_rating": accepted["rating"]},
        }
    )


class DecisionStabilityController:
    """Small reusable wrapper around :func:`evaluate_decision_stability`."""

    def __init__(self, thresholds: StabilityThresholds | Mapping[str, Any] | None = None) -> None:
        self.thresholds = _coerce_thresholds(thresholds)

    def evaluate(
        self,
        proposal: Mapping[str, Any] | None = None,
        previous_accepted_decision: Mapping[str, Any] | None = None,
        candidate_strategy_action: str | Mapping[str, Any] | None = None,
        run_quality: Any = None,
        calibrated_confidence: Any = None,
        evidence_groups: Mapping[str, Any] | Sequence[Any] | None = None,
        triggered_invalidations: Any = None,
        hard_risk: Any = None,
        *,
        pm_proposal: Mapping[str, Any] | None = None,
        strategy_action: str | Mapping[str, Any] | None = None,
        quality: Any = None,
        invalidations: Any = None,
        hard_risk_exit: Any = None,
    ) -> dict[str, Any]:
        return evaluate_decision_stability(
            proposal,
            previous_accepted_decision,
            candidate_strategy_action,
            run_quality,
            calibrated_confidence,
            evidence_groups,
            triggered_invalidations,
            hard_risk,
            pm_proposal=pm_proposal,
            strategy_action=strategy_action,
            quality=quality,
            invalidations=invalidations,
            hard_risk_exit=hard_risk_exit,
            thresholds=self.thresholds,
        )


def _coerce_thresholds(value: StabilityThresholds | Mapping[str, Any] | None) -> StabilityThresholds:
    if value is None:
        return StabilityThresholds()
    if isinstance(value, StabilityThresholds):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("thresholds must be a StabilityThresholds instance or mapping")
    known = {field.name for field in fields(StabilityThresholds)}
    values = {key: val for key, val in value.items() if key in known}
    return StabilityThresholds(**values)


def _unwrap_previous(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get("accepted_decision")
    if isinstance(nested, Mapping):
        nested_decision = nested.get("decision")
        if isinstance(nested_decision, Mapping):
            return deepcopy(dict(nested_decision))
        return deepcopy(dict(nested))
    return deepcopy(dict(value))


def _decision_point(payload: Mapping[str, Any]) -> _DecisionPoint:
    copied = deepcopy(dict(payload))
    rating = _canonical_rating(copied.get("rating"))
    allocation, allocation_key = _allocation(copied)
    return _DecisionPoint(
        payload=copied,
        rating=rating,
        score=RATING_SCORES.get(rating) if rating else None,
        allocation=allocation,
        allocation_key=allocation_key,
    )


def _canonical_rating(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _RATING_ALIASES.get(value.strip().lower())


def _allocation(payload: Mapping[str, Any]) -> tuple[float | None, str | None]:
    empty_key: str | None = None
    for key in _ALLOCATION_KEYS:
        if key in payload:
            empty_key = empty_key or key
            number = _finite_number(payload.get(key))
            if number is not None:
                return number, key
    return None, empty_key


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _strategy_action(value: str | Mapping[str, Any] | None) -> str:
    if isinstance(value, Mapping):
        value = value.get("action") or value.get("revision_action") or value.get("strategy_action")
    if not isinstance(value, str):
        return "UNKNOWN"
    normalized = value.strip().upper()
    return normalized if normalized in {"KEEP", "STRENGTHEN", "WEAKEN", "INVALIDATE", "REBUILD"} else "UNKNOWN"


def _score_quality(value: Any) -> tuple[float, str]:
    raw = value
    if isinstance(value, Mapping):
        raw = value.get("score", value.get("quality", value.get("confidence", value.get("label"))))
    if isinstance(raw, str):
        label = raw.strip().lower()
        labels = {"high": 0.85, "medium": 0.60, "low": 0.30}
        if label in labels:
            return labels[label], label
        parsed = _finite_number(label)
        if parsed is None:
            return 0.0, "low"
        raw = parsed
    score = _probability(raw)
    if score is None:
        score = 0.0
    return score, _quality_label(score)


def _score_confidence(value: Any, proposal: Mapping[str, Any]) -> tuple[float, str, bool]:
    source = "calibrated_confidence"
    raw = value
    if isinstance(value, Mapping):
        raw = value.get("score", value.get("confidence", value.get("value")))
    if raw is None:
        raw = proposal.get("calibrated_confidence", proposal.get("confidence_score"))
        source = "proposal_confidence_fallback"
    score = _probability(raw)
    if score is None:
        return 0.0, source, False
    return score, source, True


def _probability(value: Any) -> float | None:
    number = _finite_number(value)
    if number is None or number < 0:
        return None
    if number > 1:
        if number <= 100:
            number /= 100
        else:
            return None
    return number


def _quality_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _transition(previous: _DecisionPoint, proposal: _DecisionPoint, config: StabilityThresholds) -> dict[str, Any]:
    if proposal.rating is None:
        return {
            "previous_rating": previous.rating,
            "proposal_rating": None,
            "accepted_rating": None,
            "previous_target_allocation": previous.allocation,
            "proposal_target_allocation": proposal.allocation,
            "rating_distance": None,
            "movement": "invalid",
            "is_material": False,
            "is_major_reversal": False,
            "is_cross_zero_reversal": False,
        }
    if previous.rating is None:
        return {
            "previous_rating": None,
            "proposal_rating": proposal.rating,
            "accepted_rating": None,
            "previous_target_allocation": previous.allocation,
            "proposal_target_allocation": proposal.allocation,
            "rating_distance": None,
            "movement": "initial",
            "is_material": False,
            "is_major_reversal": False,
            "is_cross_zero_reversal": False,
        }

    assert previous.score is not None
    assert proposal.score is not None
    rating_distance = abs(proposal.score - previous.score)
    allocation_crosses_zero = (
        previous.allocation is not None
        and proposal.allocation is not None
        and previous.allocation * proposal.allocation < 0
    )

    allocation_direction = _allocation_direction(previous.allocation, proposal.allocation, config)
    if allocation_crosses_zero:
        movement = "cross_zero_reversal"
    elif allocation_direction:
        movement = allocation_direction
    else:
        previous_risk = _rating_risk_magnitude(previous.rating)
        proposal_risk = _rating_risk_magnitude(proposal.rating)
        if proposal_risk > previous_risk:
            movement = "risk_increase"
        elif proposal_risk < previous_risk:
            movement = "risk_reduction"
        else:
            movement = "same_state"

    return {
        "previous_rating": previous.rating,
        "proposal_rating": proposal.rating,
        "accepted_rating": None,
        "previous_target_allocation": previous.allocation,
        "proposal_target_allocation": proposal.allocation,
        "rating_distance": rating_distance,
        "movement": movement,
        "is_material": rating_distance >= 2
        or _allocation_is_material(previous.allocation, proposal.allocation, config),
        "is_major_reversal": allocation_crosses_zero,
        "is_cross_zero_reversal": allocation_crosses_zero,
    }


def _rating_risk_magnitude(rating: str | None) -> int:
    return _RATING_RISK_MAGNITUDE.get(rating or "", 0)


def _allocation_direction(previous: float | None, proposal: float | None, config: StabilityThresholds) -> str | None:
    if previous is None or proposal is None or abs(previous - proposal) < 1e-12:
        return None
    if previous * proposal < 0:
        return None
    previous_magnitude = abs(previous)
    proposal_magnitude = abs(proposal)
    if proposal_magnitude > previous_magnitude + 1e-12:
        return "risk_increase"
    if proposal_magnitude < previous_magnitude - 1e-12:
        return "risk_reduction"
    return None


def _allocation_is_material(previous: float | None, proposal: float | None, config: StabilityThresholds) -> bool:
    if previous is None or proposal is None:
        return False
    change = abs(proposal - previous)
    if change < 1e-12:
        return False
    denominator = max(abs(previous), 1e-12)
    return change / denominator >= config.material_allocation_relative_change


def _required_thresholds(transition: Mapping[str, Any], config: StabilityThresholds) -> tuple[float, float]:
    movement = transition["movement"]
    if movement == "initial":
        return config.initial_confidence, config.initial_quality
    if movement == "cross_zero_reversal":
        return config.reversal_confidence, config.reversal_quality
    if movement == "risk_increase":
        if transition["is_material"]:
            return config.increase_material_confidence, config.increase_material_quality
        return config.increase_one_step_confidence, config.increase_one_step_quality
    if movement == "risk_reduction":
        if transition["is_material"]:
            return config.reduce_material_confidence, config.reduce_material_quality
        return config.reduce_one_step_confidence, config.reduce_one_step_quality
    return config.same_confidence, config.same_quality


def _has_triggered_invalidation(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        for key in ("triggered", "active", "invalidated", "has_invalidation"):
            if key in value:
                return bool(value[key])
        if "items" in value:
            return _has_triggered_invalidation(value["items"])
        # A structured TriggeredInvalidation is itself an event; it does not
        # carry a redundant boolean flag.
        if value.get("condition_id") and value.get("evidence_ids"):
            return True
        return any(_has_triggered_invalidation(item) for item in value.values())
    if isinstance(value, Sequence):
        return any(_has_triggered_invalidation(item) for item in value)
    return bool(value)


def _independent_supporting_groups(
    value: Mapping[str, Any] | Sequence[Any] | None,
    *,
    proposal_score: int | None,
    config: StabilityThresholds,
) -> dict[str, Any]:
    entries = _evidence_entries(value)
    supporting: list[str] = []
    excluded: list[str] = []
    source_families: set[str] = set()
    for name, detail, assumed_supporting in entries:
        normalized_name = str(name).strip() or "unnamed"
        is_mapping = isinstance(detail, Mapping)
        independent = _as_bool(detail.get("independent", detail.get("is_independent", True))) if is_mapping else True
        if normalized_name.lower() in _NON_INDEPENDENT_GROUPS:
            independent = False
        family = normalized_name.lower()
        if is_mapping:
            raw_family = detail.get("source_family", detail.get("evidence_family", family))
            if isinstance(raw_family, str) and raw_family.strip():
                family = raw_family.strip().lower()
            strength = _probability(detail.get("evidence_strength", detail.get("strength", 1.0)))
            if strength is None:
                strength = 0.0
            supports = _evidence_supports_proposal(detail, proposal_score)
        else:
            strength = 1.0
            supports = assumed_supporting

        if not independent:
            excluded.append(f"{normalized_name}:not_independent")
        elif family in source_families:
            excluded.append(f"{normalized_name}:duplicate_source_family")
        elif strength < config.min_evidence_strength:
            excluded.append(f"{normalized_name}:weak_evidence")
        elif not supports:
            excluded.append(f"{normalized_name}:does_not_support_proposal")
        else:
            source_families.add(family)
            supporting.append(normalized_name)

    return {
        "independent_supporting_groups": supporting,
        "independent_supporting_group_count": len(supporting),
        "excluded_groups": excluded,
    }


def _evidence_entries(value: Mapping[str, Any] | Sequence[Any] | None) -> list[tuple[str, Any, bool]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        groups = value.get("groups")
        if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes, bytearray)):
            return _evidence_entries(groups)
        return [(str(name), detail, bool(detail) if not isinstance(detail, Mapping) else False) for name, detail in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        entries: list[tuple[str, Any, bool]] = []
        for index, detail in enumerate(value):
            if isinstance(detail, str):
                entries.append((detail, detail, True))
            elif isinstance(detail, Mapping):
                name = detail.get("group", detail.get("name", detail.get("team", f"group_{index + 1}")))
                entries.append((str(name), detail, False))
        return entries
    return []


def _evidence_supports_proposal(detail: Mapping[str, Any], proposal_score: int | None) -> bool:
    if "supports_proposal" in detail:
        return _as_bool(detail["supports_proposal"])
    if "supports" in detail:
        return _as_bool(detail["supports"])
    raw_bias = detail.get("bias", detail.get("direction", detail.get("rating")))
    if isinstance(raw_bias, str):
        bias = raw_bias.strip().lower()
        if proposal_score is not None and proposal_score > 0:
            return bias in {"bullish", "positive", "long", "buy", "overweight"}
        if proposal_score is not None and proposal_score < 0:
            return bias in {"bearish", "negative", "short", "sell", "underweight"}
        return bias in {"neutral", "hold", "flat"}
    return False


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "active", "triggered"}
    return bool(value)


def _hard_risk_details(value: Any) -> tuple[bool, dict[str, Any]]:
    if isinstance(value, bool):
        return value, {}
    if not isinstance(value, Mapping):
        return bool(value), {}
    payload = deepcopy(dict(value))
    for key in ("triggered", "active", "hard_exit", "breached", "violation"):
        if key in payload:
            return _as_bool(payload[key]), payload
    return bool(payload), payload


def _hard_risk_reason_codes(payload: Mapping[str, Any]) -> list[str]:
    reason = payload.get("reason_code", payload.get("reason"))
    if isinstance(reason, str) and reason.strip():
        return ["hard_risk_exit", reason.strip()]
    return ["hard_risk_exit"]


def _accepted_proposal(proposal: _DecisionPoint, confidence: float) -> dict[str, Any]:
    accepted = deepcopy(proposal.payload)
    assert proposal.rating is not None
    accepted["rating"] = proposal.rating
    accepted["confidence_score"] = confidence
    return accepted


def _rejected_result(
    base: Mapping[str, Any],
    proposal: _DecisionPoint,
    *,
    reasons: list[str],
    required_confidence: float | None,
    required_quality: float | None,
) -> dict[str, Any]:
    accepted = _hold_no_order(proposal)
    transition = dict(base["transition"])
    transition["accepted_rating"] = "Hold"
    return {
        **base,
        "status": "rejected",
        "proposal_accepted": False,
        "accepted": False,
        "accepted_decision": accepted,
        "execution_action": "no_order",
        "reduce_only": False,
        "reason_codes": reasons,
        "required_confidence": required_confidence,
        "required_quality": required_quality,
        "transition": transition,
    }


def _hold_no_order(proposal: _DecisionPoint) -> dict[str, Any]:
    held = deepcopy(proposal.payload)
    held["rating"] = "Hold"
    for key in _ALLOCATION_KEYS:
        if key in held:
            held[key] = None
    held["position_size_pct"] = None
    held["suggested_capital"] = 0.0
    held["execution_action"] = "no_order"
    return held


def _forced_reduce_only_decision(
    proposal: _DecisionPoint,
    previous: _DecisionPoint,
    hard_risk: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a safety exit that cannot open or reverse a position."""
    accepted = deepcopy(proposal.payload)
    requested_target, requested_key = _allocation(hard_risk)
    previous_target = previous.allocation
    target = _reduce_only_target(previous_target, requested_target)
    allocation_key = requested_key or proposal.allocation_key or previous.allocation_key or "position_size_pct"
    accepted[allocation_key] = target
    if allocation_key == "position_size_pct" or "position_size_pct" in accepted:
        accepted["position_size_pct"] = target
    accepted["suggested_capital"] = 0.0
    accepted["execution_action"] = "reduce_only"
    accepted["reduce_only"] = True
    accepted["forced_by_hard_risk"] = True

    previous_is_short = (
        previous_target is not None and previous_target < 0
    ) or (previous_target is None and previous.rating == "Sell")
    if target == 0:
        accepted["rating"] = "Buy" if previous_is_short else "Sell"
    elif previous_is_short:
        accepted["rating"] = "Overweight"
    else:
        accepted["rating"] = "Underweight"
    return accepted


def _reduce_only_target(previous: float | None, requested: float | None) -> float:
    if previous is None or abs(previous) < 1e-12:
        return 0.0
    desired = 0.0 if requested is None else requested
    if previous > 0:
        return min(max(desired, 0.0), previous)
    return max(min(desired, 0.0), previous)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _with_shadow_fields(result: dict[str, Any]) -> dict[str, Any]:
    result["would_status"] = result["status"]
    result["would_accept_proposal"] = result["proposal_accepted"]
    result["would_block_proposal"] = not result["proposal_accepted"]
    result["would_execution_action"] = result["execution_action"]
    result["would_reduce_only"] = result["reduce_only"]
    result["would_accepted_decision"] = deepcopy(result["accepted_decision"])
    result["would_reason_codes"] = deepcopy(result["reason_codes"])
    result["decision_transition"] = deepcopy(result["transition"])
    return result


__all__ = [
    "DecisionStabilityController",
    "RATING_SCORES",
    "StabilityThresholds",
    "evaluate_decision_stability",
]