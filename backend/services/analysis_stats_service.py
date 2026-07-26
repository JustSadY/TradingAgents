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

from backend.core.constants import (
    BUY_SIGNALS as _BUY_SIGNALS,
)
from backend.core.constants import (
    SELL_SIGNALS as _SELL_SIGNALS,
)
from backend.core.constants import (
    TOKENS_PER_ANALYST as _TOKENS_PER_ANALYST,
)
from backend.models.analysis import AnalysisResult
from backend.services.token_analytics_service import get_blended_rate_per_1k

_logger = logging.getLogger(__name__)


def _rate_for_model(model: str, default: float) -> float:
    # Delegates to token_analytics_service's MODEL_COSTS table — the single
    # source of truth for model pricing, so this pre-run estimate can't drift
    # from the actual post-run cost calculation.
    return get_blended_rate_per_1k(model, default)


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
    return (signal in _BUY_SIGNALS and raw_return > 0) or (signal in _SELL_SIGNALS and raw_return < 0)


# Static placeholder definition deleted to avoid returning fake/mock data in production.


async def get_ab_comparison(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    try:
        q = select(AnalysisResult).where(AnalysisResult.status == "completed")
        if user_id is not None:
            q = q.where(AnalysisResult.user_id == user_id)
        rows = (await db.execute(q)).scalars().all()
    except Exception as exc:  # tolerate an un-migrated DB
        _logger.warning("Failed to query AnalysisResult (DB may be unmigrated): %s", exc)
        rows = []

    groups: dict[str, list] = {}
    for row in rows:
        preset = _resolve_preset_name(row)
        groups.setdefault(preset, []).append(row)

    comparison = []
    for preset, runs in groups.items():
        metrics = _calculate_preset_metrics(preset, runs)
        comparison.append(metrics)
    return comparison


def _resolve_preset_name(row: AnalysisResult) -> str:
    """Resolve a display name for the preset/model combo."""
    preset = row.preset_name
    if not preset or preset.lower() in ("unknown", "unknown:unknown", "unknown/unknown"):
        prov = (row.llm_provider or "Custom").strip()
        mod = (row.llm_model or "Model").strip()
        if not prov or prov.lower() in ("unknown", "none"):
            prov = "Custom"
        if not mod or mod.lower() in ("unknown", "none"):
            mod = "Model"
        preset = f"{prov}:{mod}"
    return preset


def _calculate_preset_metrics(preset: str, runs: list[AnalysisResult]) -> dict:
    """Calculate performance metrics for a group of runs."""
    from datetime import datetime

    base_metrics = _calc_base(runs)

    runs_sorted = sorted(runs, key=lambda r: r.created_at or datetime.min, reverse=True)
    realized_metrics = _calc_realized(runs_sorted[:50])

    return {
        "preset_name": preset,
        "total_runs": base_metrics["total"],
        "avg_duration": base_metrics["avg_duration"],
        "avg_tokens": base_metrics["avg_tokens"],
        "avg_cost_usd": base_metrics["avg_cost_usd"],
        "win_rate": base_metrics["win_rate"],
        "total_graded": base_metrics["total_graded"],
        "win_rate_last_50": realized_metrics["win_rate_last_50"],
        "avg_alpha_last_50": realized_metrics["avg_alpha_last_50"],
        "avg_raw_return_last_50": realized_metrics["avg_raw_return_last_50"],
        "total_graded_last_50": realized_metrics["total_graded_last_50"],
    }


def _calc_base(runs: list[AnalysisResult]) -> dict:
    total = len(runs)
    if not total:
        return {
            "total": 0,
            "avg_duration": 0.0,
            "avg_tokens": 0,
            "avg_cost_usd": 0.0,
            "win_rate": None,
            "total_graded": 0,
        }

    durations = [r.duration_seconds for r in runs if (r.duration_seconds or 0.0) > 0]
    tokens = [((r.tokens_in or 0) + (r.tokens_out or 0)) for r in runs]
    costs = [
        ((r.tokens_in or 0) + (r.tokens_out or 0)) / 1000 * _rate_for_model(r.llm_model or "gpt-4o", 0.002)
        for r in runs
    ]
    graded = [r for r in runs if r.raw_return is not None and r.signal in (_BUY_SIGNALS | _SELL_SIGNALS)]
    wins = sum(1 for r in graded if _is_correct(r.signal, r.raw_return))

    return {
        "total": total,
        "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "avg_tokens": int(sum(tokens) / total) if tokens else 0,
        "avg_cost_usd": round(sum(costs) / total, 4) if costs else 0.0,
        "win_rate": round(wins / len(graded) * 100, 1) if graded else None,
        "total_graded": len(graded),
    }


def _calc_realized(runs: list[AnalysisResult]) -> dict:
    graded = [r for r in runs if r.raw_return is not None and r.signal in (_BUY_SIGNALS | _SELL_SIGNALS)]
    wins = sum(1 for r in graded if _is_correct(r.signal, r.raw_return))
    alphas = [r.alpha_return for r in runs if r.alpha_return is not None]
    raws = [r.raw_return for r in runs if r.raw_return is not None]

    return {
        "win_rate_last_50": round(wins / len(graded) * 100, 1) if graded else None,
        "avg_alpha_last_50": round(sum(alphas) / len(alphas) * 100, 2) if alphas else 0.0,
        "avg_raw_return_last_50": round(sum(raws) / len(raws) * 100, 2) if raws else 0.0,
        "total_graded_last_50": len(graded),
    }


async def get_signal_performance(db: AsyncSession, ticker: str | None = None, user_id: int | None = None) -> dict:
    q = select(AnalysisResult).where(AnalysisResult.status == "completed").where(AnalysisResult.raw_return.isnot(None))
    if user_id is not None:
        q = q.where(AnalysisResult.user_id == user_id)
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return {"total": 0, "win_rate": None, "avg_raw_return": None, "avg_alpha_return": None, "by_signal": {}}

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
    return {
        "total": n,
        "win_rate": round(wins / n * 100, 1),
        "avg_raw_return": round(total_raw / n * 100, 2),
        "avg_alpha_return": round(total_alpha / n * 100, 2),
        "by_signal": by_signal,
    }
