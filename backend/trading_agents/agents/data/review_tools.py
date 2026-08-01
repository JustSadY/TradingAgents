import asyncio
import logging
from datetime import UTC, datetime

import pandas as pd
from langchain_core.tools import tool

_logger = logging.getLogger(__name__)


def _past_decision_for_review(analysis) -> tuple[str, str]:
    """Choose the prior run's single final decision for a performance review.

    Old rows can retain a ``trader_plan`` for display, but a new review must
    learn from the Portfolio Manager's actual final decision rather than
    reintroducing a retired second AI as a source of truth.
    """
    final_decision = str(getattr(analysis, "final_decision", "") or "").strip()
    if final_decision:
        return final_decision, "PAST FINAL PORTFOLIO MANAGER DECISION"

    legacy_plan = str(getattr(analysis, "trader_plan", "") or "").strip()
    if legacy_plan:
        return legacy_plan, "PAST LEGACY TRADER PLAN (historical only)"
    return "", ""


@tool
async def get_past_performance_data(ticker: str, curr_date: str | None = None) -> str:
    """Retrieve historical performance reports and analyze realized returns relative to previous model suggestions for a given stock ticker."""
    if not curr_date:
        curr_date = datetime.now(UTC).strftime("%Y-%m-%d")

    past_report = None
    past_date = None

    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.analysis import list_historical_analyses
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        run_user_id = ctx.get("user_id") if ctx else None

        if run_user_id is None:
            return "No past analysis data found for this ticker."

        scope_user = type("_RunUser", (), {"id": run_user_id, "is_admin": False})()

        async with AsyncSessionLocal() as db:
            past_analyses = await list_historical_analyses(
                db, user=scope_user, ticker=ticker, before_trade_date=curr_date, limit=1
            )
            if past_analyses:
                latest = past_analyses[0]
                past_report, report_label = _past_decision_for_review(latest)
                past_date = latest.trade_date
    except Exception as e:
        _logger.warning("Failed to fetch past performance data from db for %s: %s", ticker, e)
        return "Failed to retrieve past performance data."

    if not past_report or not past_date:
        return "No past analysis data found for this ticker."

    try:
        from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv

        hist = await asyncio.to_thread(load_ohlcv, ticker, curr_date)

        hist_filtered = hist[hist["Date"] >= pd.to_datetime(past_date)]
        if hist_filtered.empty:
            return f"Found past report from {past_date}, but could not fetch price history from local cache."

        past_price = hist_filtered.iloc[0]["Close"]
        current_price = hist_filtered.iloc[-1]["Close"]
        return_pct = ((current_price - past_price) / past_price) * 100

        brief_report = past_report[:1000] + "..." if len(past_report) > 1000 else past_report

        result = (
            f"--- PAST PERFORMANCE DATA FOR {ticker} ---\n"
            f"Past Analysis Date: {past_date}\n"
            f"Price on that date: ${past_price:.2f}\n"
            f"Current Price (as of {curr_date}): ${current_price:.2f}\n"
            f"Actual Return Since Then: {return_pct:.2f}%\n"
            f"\n--- EXCERPT OF {report_label} ---\n"
            f"{brief_report}\n"
        )
        return result
    except Exception as e:
        _logger.exception("Error fetching past performance data")
        return f"Error retrieving performance data: {e}"
