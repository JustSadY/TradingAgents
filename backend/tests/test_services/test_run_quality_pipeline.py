from backend.services.analysis.run_quality import assess_run_quality


def _healthy_state() -> dict:
    return {
        "market_report": "Rating: Buy\nHealthy market evidence.",
        "news_report": "Rating: Hold\nHealthy news evidence.",
        "analysis_plan_report": "Focused analysis plan.",
        "investment_plan": "Research synthesis completed.",
        "investment_debate_state": {"history": "Bull and bear debate completed."},
        "risk_debate_state": {"history": "Risk panel completed."},
        "strategy_reconciliation_report": "## Strategy Reconciliation\nAction: KEEP",
    }


def test_healthy_pipeline_keeps_high_quality() -> None:
    quality = assess_run_quality(_healthy_state(), ["market", "news"], "Buy — accepted decision")

    assert quality["score"] == 100
    assert quality["confidence"] == "high"
    assert quality["pipeline_degradations"] == []


def test_planner_fallback_is_penalized_but_not_treated_as_critical() -> None:
    state = _healthy_state()
    state["analysis_plan_report"] = "Analysis planner unavailable; analysts will perform an independent general review."

    quality = assess_run_quality(state, ["market", "news"], "Hold — accepted decision")

    assert quality["score"] == 90
    assert quality["confidence"] == "high"
    assert quality["pipeline_degradations"] == ["analysis_planner"]
    assert quality["critical_pipeline_degraded"] is False


def test_risk_fallback_forces_low_quality_for_execution_gate() -> None:
    state = _healthy_state()
    state["risk_debate_state"] = {"history": "Risk debate error; degraded."}

    quality = assess_run_quality(state, ["market", "news"], "Buy — accepted decision")

    assert quality["score"] == 35
    assert quality["confidence"] == "low"
    assert quality["critical_pipeline_degraded"] is True
    assert "risk_debate" in quality["pipeline_degradations"]


def test_portfolio_manager_automated_fallback_remains_strongest_failure() -> None:
    quality = assess_run_quality(
        _healthy_state(),
        ["market", "news"],
        "Hold — automated fallback: Portfolio Manager unavailable.",
    )

    assert quality["score"] == 25
    assert quality["confidence"] == "low"
    assert quality["fallback_used"] is True
