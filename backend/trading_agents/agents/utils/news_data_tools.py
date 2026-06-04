from langchain_core.tools import tool
from typing import Annotated, Optional
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    return route_to_vendor("get_news", ticker, start_date, end_date)
@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[Optional[int], "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[Optional[int], "Max articles to return; omit to use the configured default"] = None,
) -> str:
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)
@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    return route_to_vendor("get_insider_transactions", ticker)
