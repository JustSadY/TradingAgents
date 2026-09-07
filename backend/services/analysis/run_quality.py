"""Post-run quality assessment: evidence completeness + pipeline degradation.

A bare final signal can hide a run where one or more guarded stages fell back.
Quality therefore combines analyst-report completeness with explicit fallback
markers from the planner/research/risk/strategy/decision stages. Automatic
execution consumes this classification through the quality gate.
"""

from __future__ import annotations

_FALLBACK_MARKER = "automated fallback"
_CRITICAL_PIPELINE_STAGES = frozenset({"research_manager", "risk_debate", "strategy_reconciler"})


def _is_degraded(text) -> bool:
    """A report is degraded when it is empty or carries a guard fallback note."""
    if not isinstance(text, str):
        return not bool(text)
    if not text.strip():
        return True
    lowered = text.lower()
    return "⚠️" in text or "unavailable" in lowered


def _pipeline_degradations(final_state: dict) -> list[str]:
    """Return stable stage codes for explicit guarded-fallback state."""
    reasons: list[str] = []

    planner = str(final_state.get("analysis_plan_report") or "").lower()
    if "analysis planner unavailable" in planner:
        reasons.append("analysis_planner")

    investment_plan = str(final_state.get("investment_plan") or "").lower()
    debate_state = final_state.get("investment_debate_state")
    debate_history = str(debate_state.get("history") or "").lower() if isinstance(debate_state, dict) else ""
    if "research manager unavailable" in investment_plan or "research branch error" in debate_history:
        reasons.append("research_manager")

    risk_state = final_state.get("risk_debate_state")
    risk_history = str(risk_state.get("history") or "").lower() if isinstance(risk_state, dict) else ""
    if "risk debate error" in risk_history or "risk debate unavailable" in risk_history:
        reasons.append("risk_debate")

    reconciliation = str(final_state.get("strategy_reconciliation_report") or "").lower()
    if "strategy reconciliation unavailable" in reconciliation:
        reasons.append("strategy_reconciler")

    return reasons


def assess_run_quality(
    final_state: dict,
    selected_analysts: list[str],
    final_decision: str | None,
) -> dict:
    """Score a completed run 0–100 and classify decision confidence.

    Analyst completeness establishes the base score. A planner fallback applies
    a modest penalty because analysts can still perform a general review. A
    critical downstream fallback (research, risk, or strategy reconciliation)
    caps confidence at low so unattended execution fails closed. Portfolio
    Manager automated fallback remains the strongest failure signal.
    """
    from backend.trading_agents.agents.analyst_registry import report_key_for

    report_keys = [rk for key in selected_analysts if (rk := report_key_for(key))]
    total = len(report_keys)
    degraded = sum(1 for rk in report_keys if _is_degraded(final_state.get(rk)))
    present = total - degraded

    fallback_used = _FALLBACK_MARKER in (final_decision or "").lower()
    pipeline_degradations = _pipeline_degradations(final_state)
    critical_pipeline_degraded = any(stage in _CRITICAL_PIPELINE_STAGES for stage in pipeline_degradations)

    completeness = (present / total) if total else 0.0
    score = round(completeness * 100)
    if "analysis_planner" in pipeline_degradations:
        score = max(0, score - 10)
    if critical_pipeline_degraded:
        score = min(score, 35)
    if fallback_used:
        score = min(score, 25)

    if fallback_used or critical_pipeline_degraded or score < 40:
        confidence = "low"
    elif score < 70:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "score": score,
        "confidence": confidence,
        "reports_total": total,
        "reports_present": present,
        "reports_degraded": degraded,
        "fallback_used": fallback_used,
        "pipeline_degradations": pipeline_degradations,
        "critical_pipeline_degraded": critical_pipeline_degraded,
    }


async def get_recent_quality_summary(db, days: int = 7) -> dict:
    """Aggregate ``AnalysisResult.quality`` over the last ``days`` for the health panel.

    Runs with no quality data (older rows, or the assessment failed and fell back
    to ``None``) are excluded from the average but counted separately so a spike
    in "unknown" isn't silently hidden.
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult

    cutoff = datetime.now(UTC) - timedelta(days=days)
    q = select(AnalysisResult.quality).where(AnalysisResult.created_at >= cutoff, AnalysisResult.status == "completed")
    rows = (await db.execute(q)).scalars().all()

    counts = {"high": 0, "medium": 0, "low": 0}
    scores: list[float] = []
    unknown = 0
    for quality in rows:
        if not isinstance(quality, dict) or "confidence" not in quality:
            unknown += 1
            continue
        confidence = quality.get("confidence")
        if confidence in counts:
            counts[confidence] += 1
        score = quality.get("score")
        if isinstance(score, (int, float)):
            scores.append(score)

    return {
        "period_days": days,
        "total_runs": len(rows),
        "unknown": unknown,
        "confidence_counts": counts,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
    }
