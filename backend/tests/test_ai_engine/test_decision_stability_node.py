from __future__ import annotations

import pytest

from backend.trading_agents.agents.base import AgentRunContext
from backend.trading_agents.agents.main import decision_stability


class _DisabledHierarchy:
    def is_enabled(self, _key: str) -> bool:
        return False

    def is_branch_enabled(self, _key: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_disabled_decision_controller_skips_reversal_verifier_and_preserves_raw_proposal(monkeypatch):
    async def should_not_run(*_args, **_kwargs):
        raise AssertionError("disabled controller must not call the reversal verifier")

    monkeypatch.setattr(decision_stability, "_verify_major_reversal", should_not_run)
    ctx = AgentRunContext(
        hierarchy=_DisabledHierarchy(),
        llms={},
        fallback_llm=object(),
        tool_nodes={},
        conditional_logic=None,
        config={"decision_stability_mode": "enforce"},
        selected_analysts=[],
    )
    node = decision_stability.create_decision_stability_controller_node(ctx)

    result = await node(
        {
            "strategy_context": {},
            "pm_proposal_json": {
                "proposed_decision": {
                    "rating": "Buy",
                    "executive_summary": "A raw proposal.",
                    "investment_thesis": "Evidence is constructive.",
                    "confidence_score": 0.9,
                    "position_size_pct": 5.0,
                    "suggested_capital": 500.0,
                },
                "rationale": "Raw PM rationale.",
            },
        }
    )

    assert result["portfolio_decision_json"]["rating"] == "Buy"
    assert result["decision_transition_json"]["mode"] == "off"
    assert result["decision_transition_json"]["canonical_enforced"] is False


@pytest.mark.asyncio
async def test_initial_rejected_proposal_is_not_mislabeled_as_initial_acceptance():
    class _EnabledHierarchy:
        def is_enabled(self, _key: str) -> bool:
            return True

        def is_branch_enabled(self, _key: str) -> bool:
            return True

    ctx = AgentRunContext(
        hierarchy=_EnabledHierarchy(),
        llms={},
        fallback_llm=object(),
        tool_nodes={},
        conditional_logic=None,
        config={"decision_stability_mode": "enforce"},
        selected_analysts=[],
    )
    node = decision_stability.create_decision_stability_controller_node(ctx)

    result = await node(
        {
            "strategy_context": {},
            "pm_proposal_json": {
                "proposed_decision": {
                    "rating": "Buy",
                    "executive_summary": "A raw proposal.",
                    "investment_thesis": "Evidence is constructive.",
                    "confidence_score": 0.9,
                    "position_size_pct": 5.0,
                    "suggested_capital": 500.0,
                },
                "rationale": "Raw PM rationale.",
            },
        }
    )

    assert result["portfolio_decision_json"]["rating"] == "Hold"
    assert result["decision_transition_json"]["outcome"] == "BLOCKED_CHANGE"


@pytest.mark.asyncio
async def test_critical_structured_invalidation_forces_reduce_only_even_in_shadow_mode():
    class _EnabledHierarchy:
        def is_enabled(self, _key: str) -> bool:
            return True

        def is_branch_enabled(self, _key: str) -> bool:
            return True

    ctx = AgentRunContext(
        hierarchy=_EnabledHierarchy(),
        llms={},
        fallback_llm=object(),
        tool_nodes={},
        conditional_logic=None,
        config={"decision_stability_mode": "shadow"},
        selected_analysts=[],
    )
    node = decision_stability.create_decision_stability_controller_node(ctx)

    result = await node(
        {
            "strategy_context": {
                "previous_accepted_decision": {
                    "rating": "Buy",
                    "executive_summary": "Existing long exposure.",
                    "investment_thesis": "Prior strategy.",
                    "confidence_score": 0.8,
                    "position_size_pct": 10.0,
                    "suggested_capital": 1_000.0,
                }
            },
            "pm_proposal_json": {
                "proposed_decision": {
                    "rating": "Buy",
                    "executive_summary": "Raw proposal before the emergency gate.",
                    "investment_thesis": "The PM did not yet incorporate the hard exit.",
                    "confidence_score": 0.9,
                    "position_size_pct": 12.0,
                    "suggested_capital": 1_200.0,
                },
                "rationale": "Raw PM rationale.",
            },
            "synthesis_json": {
                "triggered_invalidations": [
                    {
                        "condition_id": "structural_export_restriction",
                        "severity": "critical",
                        "rationale": "A critical, thesis-breaking restriction was triggered.",
                        "evidence_ids": ["restriction_notice"],
                    }
                ]
            },
        }
    )

    assert result["portfolio_decision_json"]["rating"] == "Sell"
    assert result["portfolio_decision_json"]["execution_action"] == "reduce_only"
    assert result["decision_transition_json"]["outcome"] == "EMERGENCY_RISK_EXIT"
    assert result["decision_transition_json"]["canonical_enforced"] is True
    assert "critical_thesis_invalidation" in result["decision_transition_json"]["controller_reason_codes"]
