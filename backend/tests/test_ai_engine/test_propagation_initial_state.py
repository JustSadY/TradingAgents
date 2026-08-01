"""Regression coverage for the complete analyst-report state contract."""

from backend.trading_agents.agents.runtime.agent_states import StateKeys
from backend.trading_agents.graph.propagation import Propagator


def test_initial_state_contains_every_declared_report_field() -> None:
    state = Propagator().create_initial_state("NVDA", "2026-08-01")

    assert {key: state[key] for key in StateKeys.ALL_REPORT_KEYS} == dict.fromkeys(StateKeys.ALL_REPORT_KEYS, "")
    assert state[StateKeys.AGENT_QA_REPORT] == ""
