from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve financial news articles and headlines for a given stock ticker and date range."""
    return await route_to_vendor("get_news", ticker, start_date, end_date)


@tool
async def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int | None, "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[int | None, "Max articles to return; omit to use the configured default"] = None,
) -> str:
    """Retrieve general/global market news articles and events around a given date."""
    return await route_to_vendor("get_global_news", curr_date, look_back_days, limit)


@tool
async def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve recent insider transaction logs (buys and sells by executives) for a company."""
    return await route_to_vendor("get_insider_transactions", ticker)
