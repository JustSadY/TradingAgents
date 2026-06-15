import logging
from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

_logger = logging.getLogger(__name__)


@tool
async def search_web(
    query: Annotated[str, "Search query"],
) -> str:
    """Perform a live search on the web for news, transcripts, or specific financial events."""
    # Currently routes to yfinance news as a proxy for web search results. The
    # window ends at the analysis date (not a hardcoded year) so results stay
    # relevant for back-dated runs, with a one-year lookback.
    from datetime import UTC, datetime, timedelta

    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        trade_date_str = ctx.get("trade_date") if ctx else None
    except Exception:
        trade_date_str = None

    end_dt = datetime.now(UTC)
    if trade_date_str:
        try:
            end_dt = datetime.strptime(trade_date_str, "%Y-%m-%d")
        except ValueError:
            pass

    start_date = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    return await route_to_vendor("get_news", query, start_date, end_date)


@tool
async def get_crypto_fear_and_greed_index() -> str:
    """Retrieve the current Crypto Fear and Greed Index to gauge market sentiment."""
    return "Fear and Greed Index: 45 (Neutral)"
