import logging
from datetime import UTC, datetime, timedelta

from backend.core.constants import (
    DEFAULT_HOLDING_DAYS as HOLDING_DAYS,
)
from backend.core.utils import resolve_benchmark

_logger = logging.getLogger(__name__)

from backend.services.market_data_service import calculate_returns


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

            # Generate reflection using the Reflector
            try:
                import asyncio

                from backend.trading_agents.default_config import DEFAULT_CONFIG
                from backend.trading_agents.graph.reflection import Reflector
                from backend.trading_agents.llm_clients import create_llm_client

                client = create_llm_client(
                    provider=DEFAULT_CONFIG.get("llm_provider", "openai"),
                    model=DEFAULT_CONFIG.get("llm_model", "gpt-4o-mini"),
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
    from sqlalchemy import select

    from backend.models.analysis import AnalysisResult
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    q = select(AnalysisResult).where(AnalysisResult.raw_return.isnot(None))
    if user_id is not None:
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
            # Normalize to Buy/Sell/Hold for grading
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


async def get_analyst_performance_context(db, user_id: int | None = None) -> str:
    """Return a tenant-scoped Markdown summary for AI prompt injection.

    ``AnalysisResult`` data belongs to individual users.  The analysis graph
    must never tune one user's analyst weights using another user's history.
    ``None`` remains available for explicitly global/admin maintenance uses.
    """
    try:
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
