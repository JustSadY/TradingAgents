"""Read-only analytics over stored analysis runs.

Cost estimation, the LLM A/B comparison table and signal-performance stats were
all computed inline inside ``api/analysis.py`` route handlers. They live here
now so the routes stay thin and the (previously duplicated) model cost table has
a single home.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult

_logger = logging.getLogger(__name__)

# Indicative blended USD cost per 1K tokens, keyed by substring of the model id.
MODEL_COST_PER_1K: dict[str, float] = {
    "gpt-4o-mini": 0.00015, "gpt-4o": 0.005, "gpt-4.1": 0.008,
    "claude-opus": 0.015, "claude-sonnet": 0.003, "gemini-1.5-pro": 0.007,
    "gemini-2.0": 0.00015, "gemini-2.5": 0.00015, "deepseek": 0.00014,
}
_TOKENS_PER_ANALYST = 8_000

_BUY_SIGNALS = {"Buy", "Overweight"}
_SELL_SIGNALS = {"Sell", "Underweight"}


def _rate_for_model(model: str, default: float) -> float:
    model = (model or "").lower()
    return next((v for k, v in MODEL_COST_PER_1K.items() if k in model), default)


def estimate_cost(analysts: str, debate_rounds: int, model: str) -> dict:
    analyst_list = [a.strip() for a in analysts.split(",") if a.strip()]
    n = len(analyst_list)
    tokens = n * _TOKENS_PER_ANALYST * debate_rounds + 5_000
    cost = tokens / 1000 * _rate_for_model(model, default=0.005)
    return {
        "analyst_count": n,
        "estimated_tokens": tokens,
        "estimated_cost_usd": round(cost, 4),
        "estimated_duration_min": round(n * 0.8 * debate_rounds + 1, 1),
    }


def _is_correct(signal: str | None, raw_return: float) -> bool:
    return (signal in _BUY_SIGNALS and raw_return > 0) or (
        signal in _SELL_SIGNALS and raw_return < 0
    )


# Static sample shown until enough graded runs exist to populate the panel.
_AB_PLACEHOLDER = [
    {"preset_name": "OpenAI Presets (GPT-4o)", "total_runs": 12, "avg_duration": 48.2,
     "avg_tokens": 142000, "avg_cost_usd": 0.71, "win_rate": 66.7, "total_graded": 6},
    {"preset_name": "Gemini Presets (Flash 2.5)", "total_runs": 8, "avg_duration": 22.4,
     "avg_tokens": 154000, "avg_cost_usd": 0.023, "win_rate": 60.0, "total_graded": 5},
    {"preset_name": "Claude Presets (Sonnet 3.5)", "total_runs": 6, "avg_duration": 62.1,
     "avg_tokens": 139000, "avg_cost_usd": 0.417, "win_rate": 75.0, "total_graded": 4},
]


async def get_ab_comparison(db: AsyncSession) -> list[dict]:
    try:
        rows = (await db.execute(select(AnalysisResult))).scalars().all()
    except Exception as exc:  # tolerate an un-migrated DB
        _logger.warning("Failed to query AnalysisResult (DB may be unmigrated): %s", exc)
        rows = []

    groups: dict[str, list] = {}
    for row in rows:
        preset = row.preset_name or f"{row.llm_provider or 'unknown'}:{row.llm_model or 'unknown'}"
        groups.setdefault(preset, []).append(row)

    comparison = []
    for preset, runs in groups.items():
        total = len(runs)
        durations = [r.duration_seconds for r in runs if (r.duration_seconds or 0.0) > 0]
        tokens = [((r.tokens_in or 0) + (r.tokens_out or 0)) for r in runs]
        costs = [
            ((r.tokens_in or 0) + (r.tokens_out or 0)) / 1000 * _rate_for_model(r.llm_model or "gpt-4o", 0.002)
            for r in runs
        ]
        graded = [r for r in runs if r.raw_return is not None and r.signal in (_BUY_SIGNALS | _SELL_SIGNALS)]
        wins = sum(1 for r in graded if _is_correct(r.signal, r.raw_return))
        comparison.append({
            "preset_name": preset,
            "total_runs": total,
            "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "avg_tokens": int(sum(tokens) / total) if tokens else 0,
            "avg_cost_usd": round(sum(costs) / total, 4) if costs else 0.0,
            "win_rate": round(wins / len(graded) * 100, 1) if graded else None,
            "total_graded": len(graded),
        })
    return comparison or _AB_PLACEHOLDER


async def get_signal_performance(db: AsyncSession, ticker: str | None = None) -> dict:
    q = select(AnalysisResult).where(AnalysisResult.raw_return.isnot(None))
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return {"total": 0, "win_rate": None, "avg_raw_return": None,
                "avg_alpha_return": None, "by_signal": {}}

    wins = 0
    total_raw = 0.0
    total_alpha = 0.0
    by_signal: dict[str, dict] = {}
    for r in rows:
        sig = r.signal or "Unknown"
        raw = r.raw_return or 0.0
        total_raw += raw
        total_alpha += r.alpha_return or 0.0
        correct = _is_correct(r.signal, raw)
        wins += correct
        bucket = by_signal.setdefault(sig, {"count": 0, "wins": 0, "avg_return": 0.0})
        bucket["count"] += 1
        bucket["avg_return"] += raw
        bucket["wins"] += correct

    n = len(rows)
    for bucket in by_signal.values():
        bucket["avg_return"] = round(bucket["avg_return"] / bucket["count"] * 100, 2)
        bucket["win_rate"] = round(bucket["wins"] / bucket["count"] * 100, 1)
    actionable_count = sum(1 for r in rows if r.signal in (_BUY_SIGNALS | _SELL_SIGNALS))
    return {
        "total": n,
        "win_rate": round(wins / actionable_count * 100, 1) if actionable_count else None,
        "avg_raw_return": round(total_raw / n * 100, 2),
        "avg_alpha_return": round(total_alpha / n * 100, 2),
        "by_signal": by_signal,
    }
