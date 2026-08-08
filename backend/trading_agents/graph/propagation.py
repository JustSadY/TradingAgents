from typing import Any

from backend.trading_agents.agents.runtime.agent_states import (
    InvestDebateState,
    RiskDebateState,
    StateKeys,
)


class Propagator:
    def __init__(self, max_recur_limit=100):
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        past_context: str = "",
        strategy_context: dict[str, Any] | None = None,
        analysis_mode: str = "live",
        learning_eligible: bool = True,
    ) -> dict[str, Any]:
        state = {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "strategy_context": dict(strategy_context or {}),
            "analysis_plan_json": {},
            "synthesis_json": {},
            "market_regime_json": {},
            "strategy_candidate_json": {},
            "pm_proposal_json": {},
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "portfolio_decision_json": "{}",
            "decision_transition_json": {},
            "calibrated_confidence": None,
            "analysis_mode": analysis_mode,
            "learning_eligible": bool(learning_eligible),
        }
        # Keep the state schema and its initial values in lockstep.  The
        # previous hand-written subset predated several optional analysts, so
        # their report fields only existed after a successful node update.
        # Starting every report field explicitly means a disabled, failed, or
        # dynamically registered analyst is distinguishable from a missing
        # state key throughout streaming and persistence.
        state.update(dict.fromkeys(StateKeys.ALL_REPORT_KEYS, ""))
        return state

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
