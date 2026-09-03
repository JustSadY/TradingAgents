from __future__ import annotations

from backend.trading_agents.agents.main.strategy_reconciler import (
    StrategyRevisionIntent,
    _candidate_respects_lifecycle,
    _fallback_candidate,
    _materialize_intent,
)
from backend.trading_agents.agents.schemas import (
    AssetStrategySnapshot,
    AssetStrategyStatus,
    PortfolioRating,
    ResearchBias,
    StrategyChangeStrength,
    StrategyRevisionAction,
    StrategyRevisionCandidate,
)


def _active_strategy() -> dict:
    return {
        "strategy_id": 42,
        "ticker": "NVDA",
        "asset_type": "stock",
        "status": "ACTIVE",
        "version": 3,
        "strategic_bias": "BULLISH",
        "conviction": 0.70,
        "accepted_rating": "Overweight",
        "thesis": "AI demand remains durable.",
        "key_drivers": ["Data-center demand"],
        "watch_conditions": ["Valuation"],
        "invalidation_conditions": [],
        "open_questions": [],
    }


def test_invalidated_lineage_is_rebuilt_not_silently_recreated() -> None:
    candidate = _fallback_candidate(
        {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "strategy_context": {
                "strategy_before": {
                    **_active_strategy(),
                    "status": "INVALIDATED",
                    "conviction": 0.25,
                    "thesis": "The prior demand thesis failed.",
                }
            },
            "analysis_plan_json": {"invalidations_to_check": []},
            "synthesis_json": {
                "dominant_bias": "Bearish",
                "evidence_groups": {
                    "fundamental": [
                        {
                            "evidence_id": "guidance_cut",
                            "analyst": "Earnings Analyst",
                            "evidence_group": "fundamental",
                            "bias": "Bearish",
                            "evidence_strength": "strong",
                            "claim": "Forward guidance materially deteriorated.",
                            "source_family": "corporate_fundamentals",
                        }
                    ]
                },
                "data_quality": {"level": "high", "score": 88},
                "triggered_invalidations": [],
                "unresolved_questions": ["Can demand stabilise after the guidance reset?"],
                "market_regime": {},
            },
        }
    )

    assert candidate.revision_action.value == "REBUILD"
    assert candidate.expected_version == 3
    assert candidate.strategy_before is not None
    assert candidate.strategy_after is not None
    assert candidate.strategy_after.strategy_id is None
    assert candidate.strategy_after.version == 1
    assert candidate.strategy_after.status.value == "ACTIVE"
    assert candidate.strategy_after.strategic_bias.value == "Bearish"


def test_watch_invalidation_cannot_close_an_active_strategy() -> None:
    candidate = _fallback_candidate(
        {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "strategy_context": {"strategy_before": _active_strategy()},
            "analysis_plan_json": {"invalidations_to_check": []},
            "synthesis_json": {
                "dominant_bias": "Bullish",
                "evidence_groups": {},
                "data_quality": {"level": "medium", "score": 60},
                "triggered_invalidations": [
                    {
                        "condition_id": "valuation_watch",
                        "severity": "watch",
                        "rationale": "Valuation is stretched but the thesis is intact.",
                        "evidence_ids": ["valuation_report"],
                    }
                ],
                "unresolved_questions": [],
                "market_regime": {},
            },
        }
    )

    assert candidate.revision_action is not StrategyRevisionAction.INVALIDATE
    assert candidate.strategy_after is not None
    assert candidate.strategy_after.status is AssetStrategyStatus.ACTIVE


def test_weaken_cannot_smuggle_a_strategic_bias_flip() -> None:
    before = AssetStrategySnapshot.model_validate(_active_strategy())
    after = before.model_copy(
        update={
            "version": 4,
            "conviction": 0.55,
            "strategic_bias": ResearchBias.BEARISH,
            "accepted_rating": PortfolioRating.SELL,
        }
    )
    candidate = StrategyRevisionCandidate(
        revision_action=StrategyRevisionAction.WEAKEN,
        expected_version=3,
        strategy_before=before,
        strategy_after=after,
        change_strength=StrategyChangeStrength.MATERIAL,
        revision_reason="Attempted lifecycle bypass.",
    )

    assert _candidate_respects_lifecycle(candidate, {"synthesis_json": {}}) is False


def test_weaken_intent_materializes_with_a_strictly_lower_conviction() -> None:
    state = {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "strategy_context": {"strategy_before": _active_strategy()},
        "analysis_plan_json": {"invalidations_to_check": []},
        "synthesis_json": {
            "dominant_bias": "Bullish",
            "evidence_groups": {},
            "data_quality": {"level": "medium", "score": 60},
            "triggered_invalidations": [],
            "unresolved_questions": [],
            "market_regime": {},
        },
    }
    fallback = _fallback_candidate(state)
    intent = StrategyRevisionIntent(
        revision_action=StrategyRevisionAction.WEAKEN,
        change_strength=StrategyChangeStrength.MATERIAL,
        revision_reason="Momentum and valuation evidence weakened without invalidating the thesis.",
    )

    candidate = _materialize_intent(state, intent, fallback)

    assert candidate.revision_action is StrategyRevisionAction.WEAKEN
    assert candidate.strategy_before is not None
    assert candidate.strategy_after is not None
    assert candidate.strategy_after.version == candidate.strategy_before.version + 1
    assert candidate.strategy_after.conviction < candidate.strategy_before.conviction
    assert candidate.strategy_after.strategic_bias is candidate.strategy_before.strategic_bias
    assert candidate.strategy_after.accepted_rating is candidate.strategy_before.accepted_rating


def test_zero_conviction_bias_conflict_does_not_generate_invalid_weaken() -> None:
    state = {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "strategy_context": {
            "strategy_before": {
                **_active_strategy(),
                "conviction": 0.0,
            }
        },
        "analysis_plan_json": {"invalidations_to_check": []},
        "synthesis_json": {
            "dominant_bias": "Bearish",
            "evidence_groups": {},
            "data_quality": {"level": "medium", "score": 60},
            "triggered_invalidations": [],
            "unresolved_questions": [],
            "market_regime": {},
        },
    }

    candidate = _fallback_candidate(state)

    assert candidate.revision_action is StrategyRevisionAction.KEEP
    assert candidate.strategy_before is not None
    assert candidate.strategy_after is not None
    assert candidate.strategy_before.conviction == 0.0
    assert candidate.strategy_after.conviction == 0.0
