from __future__ import annotations

from backend.services.decision_stability_service import (
    DecisionStabilityController,
    StabilityThresholds,
    evaluate_decision_stability,
)


def _proposal(rating: str, allocation: float | None = None) -> dict:
    proposal = {
        "rating": rating,
        "position_size_pct": allocation,
        "confidence_score": 0.91,
        "executive_summary": "Raw Portfolio Manager proposal.",
    }
    if allocation is not None:
        # Mirror the graph adapter: Sell with a positive magnitude is a short
        # target, while Sell 0 is flat/exit. Other ratings remain long/flat.
        proposal["target_allocation_pct"] = -allocation if rating == "Sell" and allocation > 0 else allocation
    return proposal


def _quality(score: int | float = 90) -> dict:
    return {"score": score, "confidence": "high"}


def _reversal_evidence() -> dict:
    return {
        "technical": {"bias": "bearish", "evidence_strength": 0.9},
        "fundamental": {"bias": "bearish", "evidence_strength": 0.85},
    }


def test_initial_proposal_is_accepted_and_raw_proposal_is_kept_separate() -> None:
    proposal = _proposal("Buy", 12)

    result = evaluate_decision_stability(
        proposal,
        run_quality=_quality(),
        calibrated_confidence=0.72,
    )

    assert result["status"] == "accepted"
    assert result["proposal_accepted"] is True
    assert result["pm_proposal"] == proposal
    assert result["pm_proposal"] is not result["accepted_decision"]
    assert result["accepted_decision"]["rating"] == "Buy"
    assert result["accepted_decision"]["confidence_score"] == 0.72
    assert result["execution_action"] == "order"
    assert result["transition"]["movement"] == "initial"


def test_same_state_uses_normal_threshold() -> None:
    result = evaluate_decision_stability(
        _proposal("Overweight", 10),
        _proposal("Overweight", 10),
        "KEEP",
        _quality(50),
        0.46,
    )

    assert result["status"] == "accepted"
    assert result["transition"]["movement"] == "same_state"
    assert result["required_confidence"] == 0.45


def test_asymmetric_thresholds_make_risk_increase_harder_than_risk_reduction() -> None:
    previous = _proposal("Overweight")

    increase = evaluate_decision_stability(
        _proposal("Buy"),
        previous,
        "STRENGTHEN",
        _quality(80),
        0.58,
    )
    reduction = evaluate_decision_stability(
        _proposal("Hold"),
        previous,
        "WEAKEN",
        _quality(80),
        0.58,
    )

    assert increase["status"] == "rejected"
    assert increase["transition"]["movement"] == "risk_increase"
    assert increase["required_confidence"] == 0.65
    assert "confidence_below_threshold" in increase["reason_codes"]

    assert reduction["status"] == "accepted"
    assert reduction["transition"]["movement"] == "risk_reduction"
    assert reduction["required_confidence"] == 0.50


def test_allocation_expansion_is_classified_as_risk_increase_even_when_rating_is_unchanged() -> None:
    result = evaluate_decision_stability(
        _proposal("Overweight", 20),
        _proposal("Overweight", 10),
        "KEEP",
        _quality(80),
        0.70,
    )

    assert result["status"] == "rejected"
    assert result["transition"]["movement"] == "risk_increase"
    assert result["transition"]["is_material"] is True
    assert result["required_confidence"] == 0.75


def test_buy_to_underweight_lower_long_target_is_risk_reduction_not_reversal() -> None:
    result = evaluate_decision_stability(
        _proposal("Underweight", 8),
        _proposal("Buy", 12),
        "WEAKEN",
        _quality(90),
        0.70,
    )

    assert result["status"] == "accepted"
    assert result["transition"]["movement"] == "risk_reduction"
    assert result["transition"]["is_cross_zero_reversal"] is False


def test_sell_zero_is_exit_not_short_reversal() -> None:
    result = evaluate_decision_stability(
        _proposal("Sell", 0),
        _proposal("Buy", 12),
        "INVALIDATE",
        _quality(90),
        0.95,
    )

    assert result["status"] == "accepted"
    assert result["transition"]["movement"] == "risk_reduction"
    assert result["transition"]["is_cross_zero_reversal"] is False


def test_cross_zero_reversal_needs_explicit_invalidation_and_independent_groups() -> None:
    result = evaluate_decision_stability(
        _proposal("Sell", 10),
        _proposal("Buy", 12),
        "INVALIDATE",
        _quality(),
        0.95,
        evidence_groups={"technical": {"bias": "bearish", "evidence_strength": 0.9}},
        triggered_invalidations=False,
    )

    assert result["status"] == "rejected"
    assert result["transition"]["is_cross_zero_reversal"] is True
    assert result["required_confidence"] == 0.82
    assert "reversal_invalidation_missing" in result["reason_codes"]
    assert "independent_evidence_missing" in result["reason_codes"]
    assert result["candidate_strategy_action"] == "INVALIDATE"


def test_cross_zero_reversal_accepts_only_with_high_quality_independent_confirmation() -> None:
    result = evaluate_decision_stability(
        _proposal("Sell", 10),
        _proposal("Buy", 12),
        {"action": "INVALIDATE"},
        _quality(90),
        0.90,
        evidence_groups=_reversal_evidence(),
        triggered_invalidations=[{"condition_id": "guidance_cut", "evidence_ids": ["e1"], "triggered": True}],
    )

    assert result["status"] == "accepted"
    assert result["accepted_decision"]["rating"] == "Sell"
    assert result["evidence"]["independent_supporting_group_count"] == 2
    assert result["transition"]["movement"] == "cross_zero_reversal"


def test_review_and_duplicate_source_families_do_not_satisfy_reversal_confirmation() -> None:
    evidence = {
        "technical": {"bias": "bearish", "source_family": "price", "evidence_strength": 0.9},
        "chart_pattern": {"bias": "bearish", "source_family": "price", "evidence_strength": 0.9},
        "review": {"bias": "bearish", "evidence_strength": 1.0},
    }
    result = evaluate_decision_stability(
        _proposal("Sell", 10),
        _proposal("Buy", 12),
        "INVALIDATE",
        _quality(90),
        0.90,
        evidence,
        True,
    )

    assert result["status"] == "rejected"
    assert result["evidence"]["independent_supporting_groups"] == ["technical"]
    assert "chart_pattern:duplicate_source_family" in result["evidence"]["excluded_groups"]
    assert "review:not_independent" in result["evidence"]["excluded_groups"]
    assert "independent_evidence_missing" in result["reason_codes"]


def test_cross_zero_reversal_rejects_low_quality_even_when_other_evidence_is_present() -> None:
    result = evaluate_decision_stability(
        _proposal("Sell", 10),
        _proposal("Buy", 12),
        "INVALIDATE",
        _quality(70),
        0.95,
        _reversal_evidence(),
        True,
    )

    assert result["status"] == "rejected"
    assert "run_quality_below_threshold" in result["reason_codes"]
    assert "major_reversal_requires_high_quality" in result["reason_codes"]


def test_rejected_reversal_becomes_tactical_hold_and_never_replays_previous_buy() -> None:
    previous = _proposal("Buy", 15)
    result = evaluate_decision_stability(
        _proposal("Sell", 10),
        previous,
        "INVALIDATE",
        _quality(90),
        0.60,
        _reversal_evidence(),
        True,
    )

    assert result["status"] == "rejected"
    assert result["pm_proposal"]["rating"] == "Sell"
    assert result["previous_accepted_decision"]["rating"] == "Buy"
    assert result["accepted_decision"]["rating"] == "Hold"
    assert result["accepted_decision"]["position_size_pct"] is None
    assert result["execution_action"] == "no_order"
    assert result["reduce_only"] is False


def test_hard_risk_exit_bypasses_hysteresis_and_forces_clamped_reduce_only_exit() -> None:
    result = evaluate_decision_stability(
        _proposal("Buy", 30),
        _proposal("Buy", 10),
        "KEEP",
        _quality(10),
        0.01,
        evidence_groups={},
        triggered_invalidations=False,
        hard_risk={"triggered": True, "reason_code": "stop_breached", "target_allocation_pct": -20},
    )

    assert result["status"] == "hard_risk_exit"
    assert result["proposal_accepted"] is False
    assert result["execution_action"] == "reduce_only"
    assert result["reduce_only"] is True
    assert result["accepted_decision"]["rating"] == "Sell"
    assert result["accepted_decision"]["target_allocation_pct"] == 0
    assert "stop_breached" in result["reason_codes"]


def test_strategy_weakening_cannot_be_used_to_justify_a_risk_increase() -> None:
    result = evaluate_decision_stability(
        _proposal("Buy"),
        _proposal("Overweight"),
        "WEAKEN",
        _quality(90),
        0.95,
    )

    assert result["status"] == "rejected"
    assert "strategy_action_blocks_risk_increase" in result["reason_codes"]


def test_invalid_rating_is_safe_rejection_instead_of_an_exception() -> None:
    result = evaluate_decision_stability(
        {"rating": "All in", "position_size_pct": 100},
        _proposal("Buy", 10),
        run_quality=_quality(),
        calibrated_confidence=0.9,
    )

    assert result["status"] == "rejected"
    assert result["accepted_decision"]["rating"] == "Hold"
    assert result["execution_action"] == "no_order"
    assert result["reason_codes"] == ["invalid_proposal_rating"]


def test_controller_wrapper_uses_custom_thresholds() -> None:
    controller = DecisionStabilityController(
        StabilityThresholds(initial_confidence=0.80, initial_quality=0.40),
    )

    result = controller.evaluate(
        pm_proposal=_proposal("Buy"),
        quality=_quality(50),
        calibrated_confidence=0.79,
    )

    assert result["status"] == "rejected"
    assert result["required_confidence"] == 0.80