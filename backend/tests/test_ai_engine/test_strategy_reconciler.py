from __future__ import annotations

from backend.trading_agents.agents.main.strategy_reconciler import _fallback_candidate


def test_invalidated_lineage_is_rebuilt_not_silently_recreated() -> None:
    """A later live run must preserve the causal lineage of an invalid thesis."""

    candidate = _fallback_candidate(
        {
            "company_of_interest": "NVDA",
            "asset_type": "stock",
            "strategy_context": {
                "strategy_before": {
                    "strategy_id": 42,
                    "ticker": "NVDA",
                    "asset_type": "stock",
                    "status": "INVALIDATED",
                    "version": 3,
                    "strategic_bias": "BULLISH",
                    "conviction": 0.25,
                    "accepted_rating": "Overweight",
                    "thesis": "The prior demand thesis failed.",
                    "key_drivers": ["Data-center demand"],
                    "watch_conditions": ["Replacement evidence"],
                    "invalidation_conditions": [],
                    "open_questions": [],
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
