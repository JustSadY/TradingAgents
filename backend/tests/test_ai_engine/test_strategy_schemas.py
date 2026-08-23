"""Contracts for memory-aware planning, reconciliation, and decision stability."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.trading_agents.agents.schemas import (
    AcceptedDecision,
    AnalysisPlan,
    AnalystEvidenceAssessment,
    AssetStrategySnapshot,
    AssetStrategyStatus,
    ComparisonOperator,
    DataQualityAssessment,
    DataQualityLevel,
    DecisionTransition,
    DecisionTransitionOutcome,
    EvidenceAlignment,
    EvidenceGroup,
    EvidenceItem,
    EvidenceSourceFamily,
    EvidenceStrength,
    ExecutionAction,
    InvalidationCondition,
    InvalidationKind,
    InvalidationSeverity,
    MacroRegime,
    MarketRegimeSnapshot,
    MarketTrend,
    PMDecisionProposal,
    PortfolioDecision,
    PortfolioRating,
    PriorAssumption,
    ResearchBias,
    RiskRegime,
    StrategicState,
    StrategyChangeStrength,
    StrategyRevisionAction,
    StrategyRevisionCandidate,
    SynthesisAssessment,
    TacticalAction,
    ThresholdMeasurement,
    TriggeredInvalidation,
    VolatilityRegime,
)


def _metric_invalidation(condition_id: str = "dc_growth") -> InvalidationCondition:
    return InvalidationCondition(
        condition_id=condition_id,
        statement="Data-center revenue growth falls below the thesis threshold for two quarters.",
        kind=InvalidationKind.METRIC,
        severity=InvalidationSeverity.CRITICAL,
        measurement=ThresholdMeasurement(
            metric="data_center_revenue_growth_yoy",
            operator=ComparisonOperator.LESS_THAN,
            threshold=20.0,
            unit="percent",
            observation_window="two consecutive fiscal quarters",
        ),
    )


def _regime() -> MarketRegimeSnapshot:
    return MarketRegimeSnapshot(
        trend=MarketTrend.BULL,
        volatility=VolatilityRegime.ELEVATED,
        risk=RiskRegime.RISK_ON,
        macro=MacroRegime.LATE_EXPANSION,
        confidence=0.81,
    )


def _data_quality() -> DataQualityAssessment:
    return DataQualityAssessment(
        level=DataQualityLevel.HIGH,
        score=88.0,
        available_evidence_groups=[EvidenceGroup.TECHNICAL, EvidenceGroup.FUNDAMENTAL],
    )


def _decision(rating: PortfolioRating, confidence: float) -> PortfolioDecision:
    return PortfolioDecision(
        rating=rating,
        executive_summary="Use a measured tactical response while respecting hard risk controls.",
        investment_thesis="The conclusion is grounded in the current independent evidence set.",
        confidence_score=confidence,
        # Only Hold may omit this; these fixtures cover directional ratings too.
        position_size_pct=None if rating is PortfolioRating.HOLD else 5.0,
    )


def _strategy(*, version: int, conviction: float, strategy_id: int = 17) -> AssetStrategySnapshot:
    return AssetStrategySnapshot(
        strategy_id=strategy_id,
        ticker="nvda",
        asset_type="STOCK",
        status=AssetStrategyStatus.ACTIVE,
        version=version,
        strategic_bias=ResearchBias.BULLISH,
        conviction=conviction,
        accepted_rating=PortfolioRating.OVERWEIGHT,
        thesis="AI infrastructure demand remains structurally durable.",
        key_drivers=["Hyperscaler capital expenditure", "Data-center growth"],
        watch_conditions=["Valuation premium"],
        invalidation_conditions=[_metric_invalidation()],
        open_questions=["Can gross margins remain durable?"],
        regime_assumption=_regime(),
        time_horizon="3-6 months",
    )


def test_analysis_plan_is_neutral_and_serializes_measurable_invalidations():
    plan = AnalysisPlan(
        objective="Re-test the material assumptions and risks for the asset.",
        prior_assumptions_to_test=[
            PriorAssumption(
                assumption_id="ai_demand",
                statement="AI infrastructure demand remains durable.",
                test_method="Compare current hyperscaler capital-expenditure guidance with prior expectations.",
            )
        ],
        invalidations_to_check=[_metric_invalidation()],
        unresolved_questions=["Has the valuation premium widened materially?"],
        analyst_questions={
            "technical": ["Has the trend structure changed?"],
            "fundamentals": ["Is margin deterioration structural?"],
        },
        horizon="3-6 months",
        source_strategy_version=7,
    )

    payload = plan.model_dump(mode="json")

    assert "rating" not in payload
    assert "position_size_pct" not in payload
    assert payload["analyst_questions"]["technical"] == ["Has the trend structure changed?"]
    measurement = payload["invalidations_to_check"][0]["measurement"]
    assert measurement == {
        "metric": "data_center_revenue_growth_yoy",
        "operator": "lt",
        "threshold": 20.0,
        "unit": "percent",
        "observation_window": "two consecutive fiscal quarters",
    }
    assert plan.as_json_dict() == payload

    with pytest.raises(ValidationError, match="not an executable rating"):
        AnalysisPlan(
            objective="Confirm the BUY thesis.",
            analyst_questions={"fundamentals": ["Did earnings improve?"]},
            horizon="3 months",
        )


def test_metric_invalidation_requires_an_actual_measurement_contract():
    with pytest.raises(ValidationError, match="require a measurement"):
        InvalidationCondition(
            condition_id="bad_metric",
            statement="Margins deteriorate.",
            kind=InvalidationKind.METRIC,
        )

    with pytest.raises(ValidationError, match="require event_name"):
        InvalidationCondition(
            condition_id="bad_event",
            statement="A structural restriction occurs.",
            kind=InvalidationKind.EVENT,
        )


def test_synthesis_assessment_links_all_evidence_references_and_excludes_review_independence():
    technical = EvidenceItem(
        evidence_id="technical_trend",
        analyst="Technical Analyst",
        evidence_group=EvidenceGroup.TECHNICAL,
        bias=ResearchBias.BULLISH,
        evidence_strength=EvidenceStrength.STRONG,
        claim="Price remains above its long-term trend support.",
        source_family=EvidenceSourceFamily.MARKET_DATA,
    )
    fundamental = EvidenceItem(
        evidence_id="dc_growth",
        analyst="Fundamental Analyst",
        evidence_group=EvidenceGroup.FUNDAMENTAL,
        bias=ResearchBias.BULLISH,
        evidence_strength=EvidenceStrength.MODERATE,
        claim="Data-center growth remains above the invalidation threshold.",
        source_family=EvidenceSourceFamily.CORPORATE_FUNDAMENTALS,
        related_invalidation_ids=["dc_growth"],
    )
    assessment = SynthesisAssessment(
        dominant_bias=ResearchBias.BULLISH,
        analysts=[
            AnalystEvidenceAssessment(
                analyst="Technical Analyst",
                evidence_group=EvidenceGroup.TECHNICAL,
                bias=ResearchBias.BULLISH,
                evidence_strength=EvidenceStrength.STRONG,
                evidence_ids=["technical_trend"],
            ),
            AnalystEvidenceAssessment(
                analyst="Fundamental Analyst",
                evidence_group=EvidenceGroup.FUNDAMENTAL,
                bias=ResearchBias.BULLISH,
                evidence_strength=EvidenceStrength.MODERATE,
                evidence_ids=["dc_growth"],
            ),
        ],
        evidence_groups={
            EvidenceGroup.TECHNICAL: [technical],
            EvidenceGroup.FUNDAMENTAL: [fundamental],
        },
        alignments=[
            EvidenceAlignment(
                topic="Trend and demand remain constructive.",
                evidence_ids=["technical_trend", "dc_growth"],
                evidence_groups=[EvidenceGroup.TECHNICAL, EvidenceGroup.FUNDAMENTAL],
                explanation="Separate technical and fundamental evidence support the same thesis.",
            )
        ],
        triggered_invalidations=[
            TriggeredInvalidation(
                condition_id="valuation_watch",
                severity=InvalidationSeverity.WATCH,
                rationale="The premium widened but the core growth condition did not fail.",
                evidence_ids=["dc_growth"],
            )
        ],
        unresolved_questions=["Can the valuation premium persist?"],
        data_quality=_data_quality(),
        market_regime=_regime(),
    )

    payload = assessment.model_dump(mode="json")
    assert payload["evidence_groups"]["technical"][0]["evidence_id"] == "technical_trend"
    assert payload["market_regime"]["risk"] == "risk_on"

    with pytest.raises(ValidationError, match="unknown evidence_ids"):
        SynthesisAssessment(
            **{
                **assessment.model_dump(),
                "analysts": [
                    {
                        "analyst": "Technical Analyst",
                        "evidence_group": "technical",
                        "bias": "Bullish",
                        "evidence_strength": "strong",
                        "evidence_ids": ["does_not_exist"],
                    }
                ],
            }
        )

    with pytest.raises(ValidationError, match="cannot count as independent"):
        EvidenceItem(
            evidence_id="review",
            analyst="Review Analyst",
            evidence_group=EvidenceGroup.REVIEW,
            bias=ResearchBias.BEARISH,
            evidence_strength=EvidenceStrength.MODERATE,
            claim="A historical review disagrees with the current thesis.",
            source_family=EvidenceSourceFamily.INTERNAL_REVIEW,
        )


def test_strategy_revision_enforces_versioning_and_materiality():
    before = _strategy(version=5, conviction=0.76)
    after = _strategy(version=6, conviction=0.67)
    revision = StrategyRevisionCandidate(
        revision_action=StrategyRevisionAction.WEAKEN,
        expected_version=5,
        strategy_before=before,
        strategy_after=after,
        change_strength=StrategyChangeStrength.MATERIAL,
        revision_reason="Valuation risk increased while core demand evidence remained intact.",
        regime_before=_regime(),
        regime_after=_regime(),
    )

    assert revision.model_dump(mode="json")["revision_action"] == "WEAKEN"
    assert revision.strategy_after is not None
    assert revision.strategy_after.ticker == "NVDA"
    assert revision.strategy_after.asset_type == "stock"

    # Repository snapshots use uppercase storage values; the agent contract
    # accepts them while retaining the public PortfolioRating/ResearchBias JSON.
    storage_compatible = AssetStrategySnapshot.model_validate(
        {
            **before.model_dump(mode="json"),
            "strategic_bias": "BULLISH",
            "accepted_rating": "OVERWEIGHT",
            "regime_assumption": {},
            "recorded_at": "2026-08-08T12:00:00Z",
        }
    )
    assert storage_compatible.strategic_bias is ResearchBias.BULLISH
    assert storage_compatible.accepted_rating is PortfolioRating.OVERWEIGHT
    assert storage_compatible.regime_assumption is None

    with pytest.raises(ValidationError, match="increment strategy version"):
        StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.WEAKEN,
            expected_version=5,
            strategy_before=before,
            strategy_after=_strategy(version=5, conviction=0.67),
            change_strength=StrategyChangeStrength.MATERIAL,
            revision_reason="This must not overwrite a stale version.",
        )

    with pytest.raises(ValidationError, match="requires at least one triggered invalidation"):
        StrategyRevisionCandidate(
            revision_action=StrategyRevisionAction.INVALIDATE,
            expected_version=5,
            strategy_before=before,
            change_strength=StrategyChangeStrength.MAJOR,
            revision_reason="No evidence-backed condition was supplied.",
        )


def test_rebuild_requires_an_explicitly_inactive_predecessor():
    """An LLM must not replace a live thesis by skipping INVALIDATE."""

    active_before = _strategy(version=5, conviction=0.76)
    replacement = active_before.model_copy(
        update={
            "strategy_id": None,
            "status": AssetStrategyStatus.ACTIVE,
            "version": 1,
            "conviction": 0.55,
            "thesis": "A separately evidenced replacement thesis.",
        }
    )
    candidate_args = {
        "revision_action": StrategyRevisionAction.REBUILD,
        "expected_version": 5,
        "strategy_before": active_before,
        "strategy_after": replacement,
        "change_strength": StrategyChangeStrength.MAJOR,
        "revision_reason": "The new thesis must retain an auditable predecessor.",
    }

    with pytest.raises(ValidationError, match="INVALIDATED or CLOSED predecessor"):
        StrategyRevisionCandidate(**candidate_args)

    invalidated_before = active_before.model_copy(update={"status": AssetStrategyStatus.INVALIDATED})
    rebuilt = StrategyRevisionCandidate(**{**candidate_args, "strategy_before": invalidated_before})
    assert rebuilt.revision_action is StrategyRevisionAction.REBUILD


def test_decision_transition_keeps_raw_proposal_separate_from_calibrated_hold():
    previous = _decision(PortfolioRating.BUY, 0.74)
    proposal = PMDecisionProposal(
        proposed_decision=_decision(PortfolioRating.SELL, 0.89),
        rationale="The PM sees a major deterioration in the current evidence.",
        supporting_evidence_ids=["technical_break", "margin_decline"],
        triggered_invalidation_ids=["dc_growth"],
    )
    accepted = AcceptedDecision(
        decision=_decision(PortfolioRating.HOLD, 0.67),
        calibrated_confidence=0.67,
        strategic_state=StrategicState.BULLISH_WEAKENING,
        tactical_action=TacticalAction.HOLD,
        execution_action=ExecutionAction.NO_NEW_ORDER,
    )
    transition = DecisionTransition(
        previous_accepted_decision=previous,
        pm_proposal=proposal,
        accepted_decision=accepted,
        outcome=DecisionTransitionOutcome.BLOCKED_CHANGE,
        reason="A high-magnitude reversal lacked independent confirmation on this run.",
        evidence_strength=EvidenceStrength.MODERATE,
        run_quality=_data_quality(),
    )

    payload = transition.model_dump(mode="json")
    assert payload["pm_proposal"]["proposed_decision"]["rating"] == "Sell"
    assert payload["accepted_decision"]["decision"]["rating"] == "Hold"
    assert payload["accepted_decision"]["calibrated_confidence"] == 0.67
    assert transition.proposed_rating_delta == -4
    assert transition.accepted_rating_delta == -2

    with pytest.raises(ValidationError, match="must equal calibrated_confidence"):
        AcceptedDecision(
            decision=_decision(PortfolioRating.HOLD, 0.7),
            calibrated_confidence=0.67,
            strategic_state=StrategicState.NEUTRAL,
            tactical_action=TacticalAction.HOLD,
            execution_action=ExecutionAction.NO_NEW_ORDER,
        )
