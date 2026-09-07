from __future__ import annotations

from backend.trading_agents.agents.main.strategy_reconciler import (
    StrategyRevisionIntent,
    _fallback_candidate,
    _materialize_intent,
)
from backend.trading_agents.agents.runtime.structured import _uses_deterministic_caller_fallback
from backend.trading_agents.agents.schemas import StrategyChangeStrength, StrategyRevisionAction


def _strategy(*, conviction: float) -> dict:
    return {
        "strategy_id": 42,
        "ticker": "NVDA",
        "asset_type": "stock",
        "status": "ACTIVE",
        "version": 3,
        "strategic_bias": "BULLISH",
        "conviction": conviction,
        "accepted_rating": "Overweight",
        "thesis": "AI infrastructure demand remains durable.",
        "key_drivers": ["Data-center demand"],
        "watch_conditions": ["Valuation"],
        "invalidation_conditions": [],
        "open_questions": [],
    }


def _bearish_evidence() -> dict:
    items = []
    for index in range(4):
        items.append(
            {
                "evidence_id": f"bearish_{index}",
                "analyst": f"Analyst {index}",
                "evidence_group": "fundamental",
                "bias": "Bearish",
                "evidence_strength": "strong",
                "claim": f"Independent bearish evidence {index}.",
                "source_family": "corporate_fundamentals",
            }
        )
    return {
        "dominant_bias": "Bearish",
        "evidence_groups": {"fundamental": items},
        "data_quality": {"level": "high", "score": 90},
        "triggered_invalidations": [],
        "unresolved_questions": [],
        "market_regime": {},
    }


def _state(*, conviction: float) -> dict:
    return {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "strategy_context": {"strategy_before": _strategy(conviction=conviction)},
        "analysis_plan_json": {"invalidations_to_check": []},
        "synthesis_json": _bearish_evidence(),
    }


def test_strategy_revision_intent_uses_deterministic_caller_fallback() -> None:
    assert _uses_deterministic_caller_fallback(StrategyRevisionIntent) is True


def test_zero_conviction_conflicting_high_quality_evidence_cannot_strengthen() -> None:
    candidate = _fallback_candidate(_state(conviction=0.0))

    assert candidate.revision_action is StrategyRevisionAction.KEEP
    assert candidate.strategy_before is not None
    assert candidate.strategy_after is not None
    assert candidate.strategy_before.conviction == 0.0
    assert candidate.strategy_after.conviction == 0.0


def test_strengthen_intent_is_rejected_when_synthesis_opposes_active_bias() -> None:
    state = _state(conviction=0.70)
    fallback = _fallback_candidate(state)
    assert fallback.revision_action is StrategyRevisionAction.WEAKEN

    intent = StrategyRevisionIntent(
        revision_action=StrategyRevisionAction.STRENGTHEN,
        change_strength=StrategyChangeStrength.MATERIAL,
        revision_reason="This intent contradicts the synthesis and must not be materialized.",
    )

    candidate = _materialize_intent(state, intent, fallback)

    assert candidate.revision_action is StrategyRevisionAction.WEAKEN
    assert candidate.strategy_after is not None
    assert candidate.strategy_before is not None
    assert candidate.strategy_after.conviction < candidate.strategy_before.conviction
