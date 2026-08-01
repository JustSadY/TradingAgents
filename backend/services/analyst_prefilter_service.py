"""Per-ticker analyst pre-screening.

Uses the realized outcomes already backfilled on past analyses (``raw_return``)
to find analysts whose signals on *this specific ticker* have a poor historical
hit rate, and drops them from the run so the engine doesn't spend tokens on a
voice that has been consistently wrong here.

Grading mirrors ``performance_service.get_analyst_attribution_stats`` (a Buy is
correct when the price rose, a Sell when it fell, a Hold when it barely moved)
but is scoped to one ticker and one user. Two guardrails keep it safe:
- an analyst is only droppable once it has at least ``min_samples`` graded calls
  on the ticker (so a couple of unlucky calls can't silence it);
- core always-on analysts are never dropped, and the run always keeps at least
  one analyst.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.trading_agents.agents.runtime.rating import parse_rating

_logger = logging.getLogger(__name__)

_PROTECTED_ANALYSTS = frozenset({"market", "news", "fundamentals", "social"})
_HOLD_BAND = 0.02

def _graded_correct(prediction: str, raw_return: float) -> bool | None:
    """True/False if the call can be graded, None if not actionable."""
    if prediction in ("Buy", "Overweight"):
        return raw_return > 0
    if prediction in ("Sell", "Underweight"):
        return raw_return < 0
    if prediction == "Hold":
        return abs(raw_return) <= _HOLD_BAND
    return None

def grade_analyst_winrates(rows, report_fields: dict[str, str]) -> dict[str, dict]:
    """Return ``{analyst_key: {"samples": n, "win_rate": pct}}`` over ``rows``.

    ``rows`` are AnalysisResult-like objects with ``raw_return`` set and a report
    text attribute per ``report_fields`` ({report_field: label})."""
    stats: dict[str, dict] = {}
    for field in report_fields:
        key = field.replace("_report", "")
        stats[key] = {"samples": 0, "correct": 0}

    for row in rows:
        raw_ret = getattr(row, "raw_return", None)
        if raw_ret is None:
            continue
        for field in report_fields:
            key = field.replace("_report", "")
            prediction = parse_rating(getattr(row, field, "") or "", default=None)
            if not prediction:
                continue
            graded = _graded_correct(prediction, raw_ret)
            if graded is None:
                continue
            stats[key]["samples"] += 1
            if graded:
                stats[key]["correct"] += 1

    out: dict[str, dict] = {}
    for key, s in stats.items():
        samples = s["samples"]
        out[key] = {
            "samples": samples,
            "win_rate": round(s["correct"] / samples * 100, 1) if samples else None,
        }
    return out

def select_underperformers(
    winrates: dict[str, dict],
    *,
    min_samples: int,
    max_win_rate: float,
) -> set[str]:
    """Analyst keys with enough samples AND a win rate below the threshold."""
    drop: set[str] = set()
    for key, s in winrates.items():
        if key in _PROTECTED_ANALYSTS:
            continue
        if s["win_rate"] is None or s["samples"] < min_samples:
            continue
        if s["win_rate"] < max_win_rate:
            drop.add(key)
    return drop

async def filter_analysts_by_history(
    db: AsyncSession,
    ticker: str,
    user_id: int | None,
    permitted: list[str],
    *,
    min_samples: int = 5,
    max_win_rate: float = 40.0,
) -> tuple[list[str], list[str]]:
    """Return ``(kept, dropped)`` analyst keys after pre-screening ``permitted``
    against this ticker's realized history. Never empties the list."""
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    try:
        q = (
            select(AnalysisResult)
            .where(AnalysisResult.ticker == ticker.upper())
            .where(AnalysisResult.raw_return.is_not(None))
        )
        if user_id is None:
            q = q.where(AnalysisResult.user_id.is_(None))
        else:
            q = q.where(AnalysisResult.user_id == user_id)
        rows = list((await db.execute(q)).scalars().all())
    except Exception as exc:  # noqa: BLE001 — pre-screening must never block a run
        _logger.warning("Analyst pre-screen query failed for %s: %s", ticker, exc)
        return permitted, []

    if not rows:
        return permitted, []

    report_fields = get_report_fields()
    winrates = grade_analyst_winrates(rows, report_fields)
    drop = select_underperformers(winrates, min_samples=min_samples, max_win_rate=max_win_rate)

    kept = [a for a in permitted if a not in drop]
    dropped = [a for a in permitted if a in drop]
    if not kept:
        return permitted, []
    if dropped:
        _logger.info(
            "Analyst pre-screen for %s dropped %s (win rate < %.0f%% over >= %d calls)",
            ticker.upper(),
            dropped,
            max_win_rate,
            min_samples,
        )
    return kept, dropped
