"""Post-run quality assessment: report completeness + decision confidence.

Surfaces silent degradation that a bare final signal hides — empty or fallback
("⚠️ … unavailable") analyst reports, or an automated-fallback Hold from the
Portfolio Manager. This is the visibility that would have made the "every run
returns Hold" failure obvious instead of silent.
"""

from __future__ import annotations

_FALLBACK_MARKER = "automated fallback"


def _is_degraded(text: str | None) -> bool:
    """A report is degraded when it is empty or carries a guard fallback note."""
    if not text or not text.strip():
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
