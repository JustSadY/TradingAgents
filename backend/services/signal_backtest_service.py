"""Signal-replay backtest: how did the system's own past signals on this ticker
actually perform?

``backfill_returns`` (cron) already fills ``raw_return`` / ``alpha_return`` on
completed analyses once their outcome window passes. This service aggregates
those realized outcomes per signal for the ticker being analysed and renders a
Markdown block that is injected into the run's historical context — so the
Research Manager and Portfolio Manager weigh the system's live track record on
this exact instrument before issuing the next call.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult

_logger = logging.getLogger(__name__)

_MAX_ROWS = 50
_RECENT_SHOWN = 5


def _summarize(rows: list) -> dict[str, dict]:
    """Per-signal stats over rows that have a realized raw_return."""
    stats: dict[str, dict] = {}
    for row in rows:
        if row.raw_return is None or not row.signal:
            continue
        s = stats.setdefault(row.signal, {"count": 0, "wins": 0, "total_return": 0.0})
        s["count"] += 1
        s["total_return"] += float(row.raw_return)
        # A Sell/Underweight call "wins" when the price fell.
        bearish = row.signal in ("Sell", "Underweight")
        realized = float(row.raw_return)
        if (realized < 0) if bearish else (realized > 0):
            s["wins"] += 1
    return stats


def render_signal_replay(ticker: str, rows: list) -> str:
    stats = _summarize(rows)
    if not stats:
        return ""

    md = f"=== SIGNAL REPLAY BACKTEST FOR {ticker.upper()} ===\n"
    md += (
        "The system's own past signals on this exact ticker, with the realized "
        "returns over each analysis's holding window:\n"
    )
    for signal, s in sorted(stats.items(), key=lambda kv: -kv[1]["count"]):
        avg = s["total_return"] / s["count"]
        win_rate = s["wins"] / s["count"] * 100.0
        md += f"- {signal}: {s['count']} signal(s), avg realized return {avg:+.2f}%, win rate {win_rate:.0f}%\n"

    recent = [r for r in rows if r.raw_return is not None][:_RECENT_SHOWN]
    if recent:
        md += "Most recent calls:\n"
        for r in recent:
            md += f"  - {r.trade_date}: {r.signal} -> {float(r.raw_return):+.2f}%\n"
    md += (
        "[IMPORTANT] If a signal type has a poor track record on this ticker, "
        "demand stronger evidence before repeating it; if the record is strong, "
        "that supports conviction.\n\n"
    )
    return md


async def get_signal_replay_context(db: AsyncSession, ticker: str, user_id: int | None) -> str:
    """Markdown replay summary for ``ticker`` scoped to the requesting user.

    Returns "" when there is no realized history yet (memory stays opt-in and
    the prompt stays clean for first-time tickers).
    """
    try:
        q = (
            select(AnalysisResult)
            .where(AnalysisResult.ticker == ticker.upper())
            .where(AnalysisResult.raw_return.is_not(None))
            .order_by(AnalysisResult.trade_date.desc())
            .limit(_MAX_ROWS)
        )
        if user_id is not None:
            q = q.where(AnalysisResult.user_id == user_id)
        rows = list((await db.execute(q)).scalars().all())
        return render_signal_replay(ticker, rows)
    except Exception as exc:  # noqa: BLE001 — context is best-effort, never block a run
        _logger.warning("Signal replay context failed for %s: %s", ticker, exc)
        return ""
