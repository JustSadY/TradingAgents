import asyncio
import logging
from datetime import datetime

import pandas as pd
from langchain_core.tools import tool

_logger = logging.getLogger(__name__)


@tool
async def get_past_performance_data(ticker: str, curr_date: str | None = None) -> str:
    """Retrieve historical performance reports and analyze realized returns relative to previous model suggestions for a given stock ticker."""
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")

    past_report = None
    past_date = None

    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.analysis import list_historical_analyses

        async with AsyncSessionLocal() as db:
            past_analyses = await list_historical_analyses(db, ticker=ticker, before_trade_date=curr_date, limit=1)
            if past_analyses:
                latest = past_analyses[0]
                past_report = latest.trader_plan
                past_date = latest.trade_date
    except Exception as e:
        _logger.warning("Failed to fetch past performance data from db for %s: %s", ticker, e)
        return "Failed to retrieve past performance data."

    if not past_report or not past_date:
        return "No past analysis data found for this ticker."

    try:
        from backend.trading_agents.dataflows.stockstats_utils import load_ohlcv

        # load_ohlcv is sync
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
            f"\n--- EXCERPT OF PAST TRADER PLAN ---\n"
            f"{brief_report}\n"
        )
        return result
    except Exception as e:
        _logger.error(f"Error fetching past performance data: {e}")
        return f"Error retrieving performance data: {e}"
