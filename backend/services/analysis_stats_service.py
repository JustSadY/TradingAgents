"""Read-only analytics over stored analysis runs.

Cost estimation, the LLM A/B comparison table and signal-performance stats were
all computed inline inside ``api/analysis.py`` route handlers. They live here
now so the routes stay thin and the (previously duplicated) model cost table has
a single home.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import BUY_SIGNALS as _BUY_SIGNALS
from backend.core.constants import SELL_SIGNALS as _SELL_SIGNALS
from backend.core.constants import TOKENS_PER_ANALYST as _TOKENS_PER_ANALYST
from backend.core.model_pricing import estimate_token_cost, estimate_total_token_cost, resolve_model_pricing
from backend.repositories.analysis_stats import list_completed_analyses_for_stats


def estimate_cost(analysts: str, debate_rounds: int, model: str, provider: str | None = None) -> dict:
    """Return a pre-run cost estimate from the canonical model-price catalogue."""
    analyst_list = [a.strip() for a in analysts.split(",") if a.strip()]
    n = len(analyst_list)
    tokens = n * _TOKENS_PER_ANALYST * debate_rounds + 5_000
    pricing = resolve_model_pricing(provider, model)
    cost = estimate_total_token_cost(provider, model, tokens)
    return {
        "analyst_count": n,
        "estimated_tokens": tokens,
        "estimated_cost_usd": round(cost, 4),
        "estimated_duration_min": round(n * 0.8 * debate_rounds + 1, 1),
        "pricing_source": pricing.source,
        "pricing_is_fallback": pricing.is_fallback,
    }


def _is_correct(signal: str | None, raw_return: float) -> bool:
    return (signal in _BUY_SIGNALS and raw_return > 0) or (signal in _SELL_SIGNALS and raw_return < 0)


async def get_ab_comparison(db: AsyncSession, user_id: int | None = None) -> list[dict]:
    rows = await list_completed_analyses_for_stats(db, user_id=user_id)

    groups: dict[str, list] = {}
    for row in rows:
        preset = _resolve_preset_name(row)
        groups.setdefault(preset, []).append(row)

    comparison = []
    for preset, runs in groups.items():
        metrics = _calculate_preset_metrics(preset, runs)
        comparison.append(metrics)
    return comparison


def _resolve_preset_name(row: object) -> str:
    """Resolve a display name for the preset/model combo."""
    preset = getattr(row, "preset_name", None)
    if not preset or preset.lower() in ("unknown", "unknown:unknown", "unknown/unknown"):
        prov = (getattr(row, "llm_provider", None) or "Custom").strip()
        mod = (getattr(row, "llm_model", None) or "Model").strip()
        if not prov or prov.lower() in ("unknown", "none"):
            prov = "Custom"
        if not mod or mod.lower() in ("unknown", "none"):
            mod = "Model"
        preset = f"{prov}:{mod}"
    return preset


def _calculate_preset_metrics(preset: str, runs: list[object]) -> dict:
    """Calculate performance metrics for a group of runs."""
    from datetime import datetime

    base_metrics = _calc_base(runs)

    runs_sorted = sorted(runs, key=lambda r: getattr(r, "created_at", None) or datetime.min, reverse=True)
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


def _calc_base(runs: list[object]) -> dict:
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

    durations = [getattr(r, "duration_seconds", None) for r in runs if (getattr(r, "duration_seconds", None) or 0.0) > 0]
    tokens = [((getattr(r, "tokens_in", None) or 0) + (getattr(r, "tokens_out", None) or 0)) for r in runs]
    # Runs whose model the catalogue does not price are left out of the
    # average entirely; counting them as zero would drag it down as a fact.
    costs = [
        cost
        for r in runs
        if (
            cost := estimate_token_cost(
                getattr(r, "llm_provider", None),
                getattr(r, "llm_model", None),
                int(getattr(r, "tokens_in", None) or 0),
                int(getattr(r, "tokens_out", None) or 0),
            )
        )
        is not None
    ]
    graded = [
        r
        for r in runs
        if getattr(r, "raw_return", None) is not None and getattr(r, "signal", None) in (_BUY_SIGNALS | _SELL_SIGNALS)
    ]
    wins = sum(1 for r in graded if _is_correct(getattr(r, "signal", None), r.raw_return))

    return {
        "total": total,
        "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "avg_tokens": int(sum(tokens) / total) if tokens else 0,
        "avg_cost_usd": round(sum(costs) / len(costs), 4) if costs else 0.0,
        "win_rate": round(wins / len(graded) * 100, 1) if graded else None,
        "total_graded": len(graded),
    }


def _calc_realized(runs: list[object]) -> dict:
    graded = [
        r
        for r in runs
        if getattr(r, "raw_return", None) is not None and getattr(r, "signal", None) in (_BUY_SIGNALS | _SELL_SIGNALS)
    ]
    wins = sum(1 for r in graded if _is_correct(getattr(r, "signal", None), r.raw_return))
    alphas = [r.alpha_return for r in runs if getattr(r, "alpha_return", None) is not None]
    raws = [r.raw_return for r in runs if getattr(r, "raw_return", None) is not None]

    return {
        "win_rate_last_50": round(wins / len(graded) * 100, 1) if graded else None,
        "avg_alpha_last_50": round(sum(alphas) / len(alphas) * 100, 2) if alphas else 0.0,
        "avg_raw_return_last_50": round(sum(raws) / len(raws) * 100, 2) if raws else 0.0,
        "total_graded_last_50": len(graded),
    }


async def get_signal_performance(db: AsyncSession, ticker: str | None = None, user_id: int | None = None) -> dict:
    rows = await list_completed_analyses_for_stats(
        db,
        user_id=user_id,
        ticker=ticker,
        require_raw_return=True,
    )
    if not rows:
        return {"total": 0, "win_rate": None, "avg_raw_return": None, "avg_alpha_return": None, "by_signal": {}}

    wins = 0
    total_raw = 0.0
    total_alpha = 0.0
    by_signal: dict[str, dict] = {}
    for r in rows:
        sig = getattr(r, "signal", None) or "Unknown"
        raw = getattr(r, "raw_return", None) or 0.0
        total_raw += raw
        total_alpha += getattr(r, "alpha_return", None) or 0.0
        correct = _is_correct(getattr(r, "signal", None), raw)
        wins += correct
        bucket = by_signal.setdefault(sig, {"count": 0, "wins": 0, "avg_return": 0.0})
        bucket["count"] += 1
        bucket["avg_return"] += raw
        bucket["wins"] += correct

    n = len(rows)
    for bucket in by_signal.values():
        c = bucket["count"]
        if c > 0:
            bucket["avg_return"] = round(bucket["avg_return"] / c * 100, 2)
            bucket["win_rate"] = round(bucket["wins"] / c * 100, 1)
        else:
            bucket["avg_return"] = 0.0
            bucket["win_rate"] = 0.0
    return {
        "total": n,
        "win_rate": round(wins / n * 100, 1),
        "avg_raw_return": round(total_raw / n * 100, 2),
        "avg_alpha_return": round(total_alpha / n * 100, 2),
        "by_signal": by_signal,
    }
