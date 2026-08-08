from __future__ import annotations

import pytest

from backend.trading_agents.agents.base import AgentRunContext
from backend.trading_agents.agents.main import decision_stability


class _DisabledHierarchy:
    def is_enabled(self, _key: str) -> bool:
        return False

    def is_branch_enabled(self, _key: str) -> bool:
        return False


class _EnabledHierarchy:
    def is_enabled(self, _key: str) -> bool:
        return True

    def is_branch_enabled(self, _key: str) -> bool:
        return True


def _ctx(mode: str):
    return AgentRunContext(
        hierarchy=_EnabledHierarchy(),
        llms={},
        fallback_llm=object(),
        tool_nodes={},
        conditional_logic=None,
        config={"decision_stability_mode": mode},
        selected_analysts=[],
    )


def _previous_buy() -> dict:
    return {
        "rating": "Buy",
        "executive_summary": "Existing long exposure.",
        "investment_thesis": "Prior strategy.",
        "confidence_score": 0.8,
        "position_size_pct": 10.0,
        "suggested_capital": 1_000.0,
    }


def _raw_buy() -> dict:
    return {
        "proposed_decision": {
            "rating": "Buy",
            "executive_summary": "Raw proposal.",
            "investment_thesis": "Current evidence remains constructive.",
            "confidence_score": 0.9,
            "position_size_pct": 12.0,
            "suggested_capital": 1_200.0,
        },
        "rationale": "Raw PM rationale.",
    }


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

    result = await node({"strategy_context": {}, "pm_proposal_json": _raw_buy()})

    assert result["portfolio_decision_json"]["rating"] == "Buy"
    assert result["decision_transition_json"]["mode"] == "off"
    assert result["decision_transition_json"]["canonical_enforced"] is False


@pytest.mark.asyncio
async def test_initial_rejected_proposal_is_not_mislabeled_as_initial_acceptance():
    node = decision_stability.create_decision_stability_controller_node(_ctx("enforce"))

    result = await node({"strategy_context": {}, "pm_proposal_json": _raw_buy()})

    assert result["portfolio_decision_json"]["rating"] == "Hold"
    assert result["decision_transition_json"]["outcome"] == "BLOCKED_CHANGE"


@pytest.mark.asyncio
async def test_critical_thesis_invalidation_is_counterfactual_only_in_shadow_mode():
    """Research invalidations cannot promote themselves to application hard risk."""
    node = decision_stability.create_decision_stability_controller_node(_ctx("shadow"))

    result = await node(
        {
            "strategy_context": {"previous_accepted_decision": _previous_buy()},
            "pm_proposal_json": _raw_buy(),
            "synthesis_json": {
                "triggered_invalidations": [
                    {
                        "condition_id": "structural_export_restriction",
                        "severity": "critical",
                        "rationale": "A thesis-breaking restriction was validated.",
                        "evidence_ids": ["restriction_notice"],
                    }
                ]
            },
        }
    )

    # Shadow preserves the physical PM proposal regardless of what the
    # controller would have done counterfactually.
    assert result["portfolio_decision_json"]["rating"] == "Buy"
    assert result["decision_transition_json"]["canonical_enforced"] is False
    assert result["decision_transition_json"]["outcome"] != "EMERGENCY_RISK_EXIT"
    assert "critical_thesis_invalidation" not in result["decision_transition_json"]["controller_reason_codes"]


@pytest.mark.asyncio
async def test_explicit_application_hard_risk_still_enforces_reduce_only_in_shadow_mode():
    node = decision_stability.create_decision_stability_controller_node(_ctx("shadow"))

    result = await node(
        {
            "strategy_context": {"previous_accepted_decision": _previous_buy()},
            "pm_proposal_json": _raw_buy(),
            "hard_risk_exit": {
                "triggered": True,
                "reason_code": "stop_breached",
                "target_allocation_pct": 0,
            },
        }
    )

    assert result["portfolio_decision_json"]["rating"] == "Sell"
    assert result["portfolio_decision_json"]["execution_action"] == "reduce_only"
    assert result["decision_transition_json"]["outcome"] == "EMERGENCY_RISK_EXIT"
    assert result["decision_transition_json"]["canonical_enforced"] is True
    assert "stop_breached" in result["decision_transition_json"]["controller_reason_codes"]