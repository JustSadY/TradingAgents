import logging
from datetime import date, datetime, timedelta, timezone
from backend.core.utils import resolve_benchmark
from backend.core.constants import (
    BUY_SIGNALS as _BUY_SIGNALS,
    SELL_SIGNALS as _SELL_SIGNALS,
    DEFAULT_HOLDING_DAYS as HOLDING_DAYS,
)

_logger = logging.getLogger(__name__)

async def backfill_returns(db) -> int:
    from sqlalchemy import select
    from backend.models.analysis import AnalysisResult
    from backend.models.settings import AppSettings
    from backend.trading_agents.dataflows.config import get_config

    cutoff = (datetime.now(timezone.utc) - timedelta(days=HOLDING_DAYS + 2)).strftime("%Y-%m-%d")
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
            res_settings = await db.execute(
                select(AppSettings).where(AppSettings.user_id == row.user_id)
            )
            settings_obj = res_settings.scalar_one_or_none()
            if settings_obj:
                bt = getattr(settings_obj, "benchmark_ticker", None)
                if bt:
                    row_config["benchmark_ticker"] = bt

        benchmark = resolve_benchmark(row.ticker, row_config)

        raw, alpha, days = await _fetch_returns_async(row.ticker, row.trade_date, benchmark=benchmark)
        if raw is not None:
            row.raw_return = raw
            row.alpha_return = alpha
            row.holding_days = days
            
            # Generate reflection using the Reflector
            try:
                from backend.trading_agents.graph.reflection import Reflector
                from backend.trading_agents.llm_clients import create_llm_client
                from backend.trading_agents.default_config import DEFAULT_CONFIG
                
                # Use a lightweight client for reflection
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

            updated += 1
    if updated:
        await db.commit()
    _logger.info("Performance backfill: updated %d rows with custom benchmarks", updated)
    return updated

async def _fetch_returns_async(ticker: str, trade_date: str, holding_days: int = HOLDING_DAYS, benchmark: str = "SPY"):
    import asyncio
    return await asyncio.to_thread(_fetch_returns_sync, ticker, trade_date, holding_days, benchmark)
def _fetch_returns_sync(ticker: str, trade_date: str, holding_days: int = HOLDING_DAYS, benchmark: str = "SPY"):
    try:
        import yfinance as yf
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days + 7)
        end_str = end.strftime("%Y-%m-%d")
        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)
        if len(stock) < 2 or len(bench) < 2:
            return None, None, None
        actual = min(holding_days, len(stock) - 1, len(bench) - 1)
        raw = float((stock["Close"].iloc[actual] - stock["Close"].iloc[0]) / stock["Close"].iloc[0])
        bench_r = float((bench["Close"].iloc[actual] - bench["Close"].iloc[0]) / bench["Close"].iloc[0])
        return round(raw, 4), round(raw - bench_r, 4), actual
    except Exception as exc:
        _logger.debug("Return fetch failed %s %s with bench %s: %s", ticker, trade_date, benchmark, exc)
        return None, None, None
async def get_analyst_attribution_stats(db) -> dict:
    from sqlalchemy import select
    from backend.models.analysis import AnalysisResult
    from backend.trading_agents.agents.analyst_registry import get_report_fields
    
    q = select(AnalysisResult).where(AnalysisResult.raw_return.isnot(None))
    result = await db.execute(q)
    rows = result.scalars().all()
    
    # Dynamically build analyst map from registry
    report_fields = get_report_fields()
    analysts = {
        rf.replace("_report", ""): {"label": label, "report_field": rf}
        for rf, label in report_fields.items()
    }
    
    stats = {
        k: {"key": k, "label": val["label"], "total_predictions": 0, "correct_predictions": 0, "win_rate": 50.0}
        for k, val in analysts.items()
    }
    import re
    def _extract(report_text: str) -> str | None:
        if not report_text:
            return None
        ratings_match = re.search(r'\*\*(buy|overweight|hold|underweight|sell)\*\*', report_text, re.IGNORECASE)
        if ratings_match:
            val = ratings_match.group(1).lower()
            if val in ("buy", "overweight"):
                return "Buy"
            if val in ("sell", "underweight"):
                return "Sell"
            return "Hold"
        text = report_text.lower()
        if re.search(r'\b(buy|bullish|overweight)\b', text):
            return "Buy"
        if re.search(r'\b(sell|bearish|underweight)\b', text):
            return "Sell"
        if re.search(r'\b(hold|neutral)\b', text):
            return "Hold"
        return None
    for row in rows:
        for key, config in analysts.items():
            report_text = getattr(row, config["report_field"], "")
            pred = _extract(report_text)
            if not pred:
                continue
            raw_ret = row.raw_return
            is_correct = False
            has_graded = False
            if pred == "Buy":
                has_graded = True
                is_correct = (raw_ret > 0)
            elif pred == "Sell":
                has_graded = True
                is_correct = (raw_ret < 0)
            elif pred == "Hold":
                has_graded = True
                is_correct = (abs(raw_ret) <= 0.02)
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
    attribution_list = list(stats.values())
    total_runs_evaluated = sum(s["total_predictions"] for s in attribution_list)
    return {
        "attribution": attribution_list,
        "total_evaluated_runs": total_runs_evaluated
    }


async def get_analyst_performance_context(db) -> str:
    """Return a Markdown summary of analyst performance weights for AI injection."""
    try:
        attribution_data = await get_analyst_attribution_stats(db)
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
