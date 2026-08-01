"""Post-run quality assessment: report completeness + decision confidence.

Surfaces silent degradation that a bare final signal hides — empty or fallback
("⚠️ … unavailable") analyst reports, or an automated-fallback Hold from the
Portfolio Manager. This is the visibility that would have made the "every run
returns Hold" failure obvious instead of silent.
"""

from __future__ import annotations

_FALLBACK_MARKER = "automated fallback"

def _is_degraded(text) -> bool:
    """A report is degraded when it is empty or carries a guard fallback note.

    Report state values are expected to be strings, but this is defensive
    against any non-string value ending up in state (never crash on it, treat
    it as present as long as it's truthy).
    """
    if not isinstance(text, str):
        return not bool(text)
    if not text.strip():
        return True
    return "⚠️" in text or "unavailable" in text.lower()

def assess_run_quality(
    final_state: dict,
    selected_analysts: list[str],
    final_decision: str | None,
) -> dict:
    """Score a completed run 0–100 and classify decision confidence.

    - completeness = share of the selected analysts that produced a usable report
    - an automated-fallback final decision caps the score and forces low confidence
    """
    from backend.trading_agents.agents.analyst_registry import report_key_for

    report_keys = [rk for key in selected_analysts if (rk := report_key_for(key))]
    total = len(report_keys)
    degraded = sum(1 for rk in report_keys if _is_degraded(final_state.get(rk)))
    present = total - degraded

    fallback_used = _FALLBACK_MARKER in (final_decision or "").lower()

    completeness = (present / total) if total else 0.0
    score = round(completeness * 100)
    if fallback_used:
        score = min(score, 25)

    if fallback_used or score < 40:
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
