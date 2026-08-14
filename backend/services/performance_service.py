import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.constants import (
    DEFAULT_HOLDING_DAYS as HOLDING_DAYS,
)
from backend.core.utils import resolve_benchmark
from backend.services.market_data_service import calculate_returns

_logger = logging.getLogger(__name__)

_WEIGHT_PRIOR_STRENGTH = 8.0
_WEIGHT_COMPONENTS = (
    ("global", 0.40),
    ("ticker", 0.25),
    ("regime", 0.20),
    ("recent", 0.15),
)
_REGIME_KEYS = ("trend", "volatility", "risk", "macro")


def _analysis_regime(row: object) -> dict[str, str]:
    raw = getattr(row, "market_regime_json", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = None
    if not isinstance(raw, dict):
        return {}
    return {
        key: str(raw[key]).strip().lower()
        for key in _REGIME_KEYS
        if raw.get(key) is not None and str(raw[key]).strip()
    }


def _normalise_regime(regime: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(regime, dict):
        return {}
    return {
        key: str(regime[key]).strip().lower()
        for key in _REGIME_KEYS
        if regime.get(key) is not None and str(regime[key]).strip()
    }


def _is_matching_regime(row: object, current_regime: dict[str, str]) -> bool:
    """Require a meaningful overlap, not a coincidental one-field match."""

    if not current_regime:
        return False
    observed = _analysis_regime(row)
    shared = [key for key in _REGIME_KEYS if key in current_regime and key in observed]
    if not shared:
        return False
    matches = sum(current_regime[key] == observed[key] for key in shared)
    required = 2 if len(shared) >= 2 else 1
    return matches >= required


def _is_recent(row: object, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    try:
        observed = datetime.fromisoformat(str(getattr(row, "trade_date", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    return observed >= now - timedelta(days=90)


def _prediction_success(report: object, raw_return: object) -> bool | None:
    """Score one analyst report with the existing five-tier rating semantics."""

    from backend.trading_agents.agents.runtime.rating import parse_rating

    prediction = parse_rating(str(report or ""), default=None)
    if not prediction:
        return None
    if prediction in ("Overweight", "Buy"):
        prediction = "Buy"
    elif prediction in ("Underweight", "Sell"):
        prediction = "Sell"
    try:
        realized = float(raw_return)
    except (TypeError, ValueError):
        return None
    if prediction == "Buy":
        return realized > 0
    if prediction == "Sell":
        return realized < 0
    if prediction == "Hold":
        return abs(realized) <= 0.02
    return None


def _posterior_accuracy(successes: int, count: int, *, prior_mean: float = 0.5) -> float:
    return (successes + prior_mean * _WEIGHT_PRIOR_STRENGTH) / (count + _WEIGHT_PRIOR_STRENGTH)


def _regime_aware_weight_rows(
    rows: list[object],
    *,
    ticker: str,
    current_regime: dict[str, Any] | None,
    report_fields: dict[str, str],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Compute shrinkage-based per-analyst weights from resolved outcomes.

    A sparse ticker/regime slice is never allowed to overwhelm the global
    baseline.  Each local score is a beta-binomial posterior anchored on the
    analyst's global posterior, and its contribution grows gradually with the
    sample count.  This is deliberately compact enough to send to an LLM
    without exposing per-run user data.
    """

    normalized_regime = _normalise_regime(current_regime)
    counters: dict[str, dict[str, list[int]]] = {
        key: {component: [0, 0] for component, _ in _WEIGHT_COMPONENTS}
        for key in (field.removesuffix("_report") for field in report_fields)
    }
    ticker = ticker.upper()
    for row in rows:
        ticker_match = str(getattr(row, "ticker", "")).upper() == ticker
        regime_match = _is_matching_regime(row, normalized_regime)
        recent_match = _is_recent(row, now=now)
        for report_field in report_fields:
            analyst = report_field.removesuffix("_report")
            success = _prediction_success(getattr(row, report_field, ""), getattr(row, "raw_return", None))
            if success is None:
                continue
            counters[analyst]["global"][0] += 1
            counters[analyst]["global"][1] += int(success)
            if ticker_match:
                counters[analyst]["ticker"][0] += 1
                counters[analyst]["ticker"][1] += int(success)
            if regime_match:
                counters[analyst]["regime"][0] += 1
                counters[analyst]["regime"][1] += int(success)
            if recent_match:
                counters[analyst]["recent"][0] += 1
                counters[analyst]["recent"][1] += int(success)

    output: list[dict[str, Any]] = []
    for report_field, label in report_fields.items():
        analyst = report_field.removesuffix("_report")
        counts = counters[analyst]
        global_count, global_successes = counts["global"]
        global_accuracy = _posterior_accuracy(global_successes, global_count)
        weighted_accuracy = 0.0
        applied_weight = 0.0
        metrics: dict[str, Any] = {}
        for component, base_weight in _WEIGHT_COMPONENTS:
            count, successes = counts[component]
            accuracy = _posterior_accuracy(successes, count, prior_mean=global_accuracy)
            # Local relevance is smoothly shrunk toward the global result;
            # 2/2 cannot become a spurious 100%-reliable specialist.
            reliability = 1.0 if component == "global" else count / (count + _WEIGHT_PRIOR_STRENGTH)
            component_weight = base_weight * reliability
            weighted_accuracy += component_weight * accuracy
            applied_weight += component_weight
            metrics[f"{component}_samples"] = count
            metrics[f"{component}_accuracy"] = round(accuracy * 100, 1)
        effective_accuracy = weighted_accuracy / applied_weight if applied_weight else global_accuracy
        output.append(
            {
                "key": analyst,
                "label": label,
                **metrics,
                "effective_accuracy": round(effective_accuracy * 100, 1),
                # We normalise this below; the small floor avoids an analyst
                # disappearing solely because it has no resolved observations.
                "_raw_weight": max(0.05, effective_accuracy),
            }
        )

    total = sum(item["_raw_weight"] for item in output) or 1.0
    for item in output:
        item["effective_weight"] = round(100.0 * item.pop("_raw_weight") / total, 1)
    return output


async def get_regime_aware_analyst_attribution_stats(
    db,
    *,
    user_id: int | None,
    ticker: str,
    current_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return privacy-scoped Bayesian analyst weights for one live run."""

    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    query = (
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.isnot(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .where(AnalysisResult.status == "completed")
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    rows = list((await db.execute(query)).scalars().all())
    report_fields = get_report_fields()
    return {
        "method": "beta_binomial_global_ticker_regime_recency_v1",
        "ticker": ticker.upper(),
        "regime": _normalise_regime(current_regime),
        "attribution": _regime_aware_weight_rows(
            rows,
            ticker=ticker,
            current_regime=current_regime,
            report_fields=report_fields,
        ),
        "total_resolved_runs": len(rows),
    }

async def backfill_returns(db) -> int:
    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult
    from backend.models.settings import AppSettings
    from backend.trading_agents.dataflows.config import get_config

    cutoff = (datetime.now(UTC) - timedelta(days=HOLDING_DAYS + 2)).strftime("%Y-%m-%d")
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.is_(None))
        .where(AnalysisResult.signal.isnot(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .where(AnalysisResult.status == "completed")
        .where(AnalysisResult.trade_date <= cutoff)
        .limit(50)
    )
    rows = result.scalars().all()
    updated = 0
    config = get_config()

    for row in rows:
        row_config = dict(config)
        if row.user_id:
            res_settings = await db.execute(select(AppSettings).where(AppSettings.user_id == row.user_id))
            settings_obj = res_settings.scalar_one_or_none()
            if settings_obj:
                bt = getattr(settings_obj, "benchmark_ticker", None)
                if bt:
                    row_config["benchmark_ticker"] = bt

        benchmark = resolve_benchmark(row.ticker, row_config)

        raw, alpha, days = await calculate_returns(
            row.ticker, row.trade_date, holding_days=HOLDING_DAYS, benchmark=benchmark
        )
        if raw is not None:
            row.raw_return = raw
            row.alpha_return = alpha
            row.holding_days = days

            try:
                import asyncio

                from backend.trading_agents.default_config import DEFAULT_CONFIG
                from backend.trading_agents.graph.reflection import Reflector
                from backend.trading_agents.llm_clients import create_llm_client

                client = create_llm_client(
                    provider=DEFAULT_CONFIG.get("llm_provider", "openai"),
                    model=DEFAULT_CONFIG.get("llm_model", "gpt-5.6-luna"),
                )
                reflector = Reflector(client.get_llm())

                reflection = await asyncio.to_thread(
                    reflector.reflect_on_final_decision,
                    final_decision=row.final_decision,
                    raw_return=raw,
                    alpha_return=alpha,
                    benchmark_name=benchmark,
                )
                row.reflection = reflection
            except Exception as ref_exc:
                _logger.warning("Could not generate reflection for analysis_id=%s: %s", row.id, ref_exc)

            from backend.services.memory_service import record_episode

            await record_episode(
                user_id=row.user_id,
                ticker=row.ticker,
                trade_date=row.trade_date,
                signal=row.signal,
                situation_text=(getattr(row, "market_report", "") or "") or (row.final_decision or ""),
                decision=row.final_decision or "",
                raw_return=raw,
                alpha_return=alpha,
                reflection=row.reflection or "",
            )

            updated += 1
    if updated:
        await db.commit()
    _logger.info("Performance backfill: updated %d rows with custom benchmarks", updated)
    return updated

async def get_analyst_attribution_stats(db, user_id: int | None = None) -> dict:
    """Return attribution statistics for one tenant or the system scope.

    ``None`` means system-owned analysis rows (``user_id IS NULL``), never
    every tenant.  A future administrative all-user aggregate must use an
    explicitly named function so it cannot be injected into a system run by
    accident.
    """
    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    q = (
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.isnot(None))
        .where(AnalysisResult.learning_eligible.is_(True))
    )
    if user_id is None:
        q = q.where(AnalysisResult.user_id.is_(None))
    else:
        q = q.where(AnalysisResult.user_id == user_id)
    result = await db.execute(q)
    rows = result.scalars().all()

    report_fields = get_report_fields()
    analysts = {rf.replace("_report", ""): {"label": label, "report_field": rf} for rf, label in report_fields.items()}

    stats = {
        k: {"key": k, "label": val["label"], "total_predictions": 0, "correct_predictions": 0, "win_rate": 50.0}
        for k, val in analysts.items()
    }
    from backend.trading_agents.agents.runtime.rating import parse_rating

    for row in rows:
        for key, config in analysts.items():
            report_text = getattr(row, config["report_field"], "")
            pred = parse_rating(report_text, default=None)
            if not pred:
                continue
            if pred in ("Overweight", "Buy"):
                pred = "Buy"
            elif pred in ("Underweight", "Sell"):
                pred = "Sell"

            raw_ret = row.raw_return
            is_correct = False
            has_graded = False
            if pred == "Buy":
                has_graded = True
                is_correct = raw_ret > 0
            elif pred == "Sell":
                has_graded = True
                is_correct = raw_ret < 0
            elif pred == "Hold":
                has_graded = True
                is_correct = abs(raw_ret) <= 0.02
            if has_graded:
                stats[key]["total_predictions"] += 1
                if is_correct:
                    stats[key]["correct_predictions"] += 1
    win_rates = {}
    for key, s in stats.items():
        total = s["total_predictions"]
        correct = s["correct_predictions"]
        if total > 0:
            s["win_rate"] = round((correct / total) * 100, 1)
        else:
            s["win_rate"] = 50.0
        win_rates[key] = s["win_rate"]
    sum_win_rates = sum(win_rates.values())
    for key, s in stats.items():
        if sum_win_rates > 0:
            s["weight"] = round((win_rates[key] / sum_win_rates) * 100, 1)
        else:
            s["weight"] = round(100.0 / len(stats), 1)
    from backend.services.analyst_prefilter_service import _PROTECTED_ANALYSTS

    chronic_min_samples = 10
    chronic_max_win_rate = 40.0
    for key, s in stats.items():
        s["chronic_underperformer"] = (
            key not in _PROTECTED_ANALYSTS
            and s["total_predictions"] >= chronic_min_samples
            and s["win_rate"] < chronic_max_win_rate
        )

    attribution_list = list(stats.values())
    total_runs_evaluated = sum(s["total_predictions"] for s in attribution_list)
    return {"attribution": attribution_list, "total_evaluated_runs": total_runs_evaluated}

async def get_analyst_performance_context(
    db,
    user_id: int | None = None,
    *,
    ticker: str | None = None,
    current_regime: dict[str, Any] | None = None,
    regime_aware: bool = False,
) -> str:
    """Return a tenant-scoped Markdown summary for AI prompt injection.

    ``AnalysisResult`` data belongs to individual users.  The analysis graph
    must never tune one user's analyst weights using another user's history.
    ``None`` selects only system-owned analysis rows; it is not an all-user
    administrative aggregate.
    """
    try:
        if regime_aware and ticker:
            attribution_data = await get_regime_aware_analyst_attribution_stats(
                db,
                user_id=user_id,
                ticker=ticker,
                current_regime=current_regime,
            )
            attribution = attribution_data.get("attribution") or []
            if not attribution:
                return ""
            md = "=== REGIME-AWARE ANALYST PERFORMANCE & WEIGHTS ===\n"
            md += (
                "Effective weights use beta-binomial shrinkage across global, ticker-specific, "
                "matching-regime, and recent accuracy. Sparse local samples are deliberately "
                "pulled back toward the global baseline.\n"
            )
            for att in attribution:
                md += (
                    f"- {att['label']}: Effective Accuracy = {att['effective_accuracy']}%, "
                    f"Weight = {att['effective_weight']}% "
                    f"(global {att['global_accuracy']}%/{att['global_samples']}, "
                    f"ticker {att['ticker_accuracy']}%/{att['ticker_samples']}, "
                    f"regime {att['regime_accuracy']}%/{att['regime_samples']}, "
                    f"recent {att['recent_accuracy']}%/{att['recent_samples']})\n"
                )
            md += "\n[IMPORTANT] Treat these as evidence-quality priors, not as a substitute for current source-grounded evidence.\n\n"
            return md

        attribution_data = await get_analyst_attribution_stats(db, user_id=user_id)
        if not attribution_data.get("attribution"):
            return ""
        md = "=== ANALYST PERFORMANCE ATTRIBUTION & WEIGHTS ===\n"
        md += "Below are the historical win rates and normalized voting weights assigned to each analyst based on empirical accuracy:\n"
        for att in attribution_data["attribution"]:
            md += f"- {att['label']}: Win Rate = {att['win_rate']}%, Assigned Weight = {att['weight']}%\n"
        md += "\n[IMPORTANT] During decision synthesis, discount opinions of analysts with lower weights and heavily prioritize opinions of analysts with higher weights.\n\n"
        return md
    except Exception as e:
        _logger.warning("Could not load analyst attribution stats (skipping): %s", e)
        return ""
