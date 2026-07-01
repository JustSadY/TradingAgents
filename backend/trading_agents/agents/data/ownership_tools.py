from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_institutional_holdings(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve institutional (13F) ownership, major-holder breakdown, and top mutual-fund holders for a company."""
    return await route_to_vendor("get_institutional_holdings", ticker)


@tool
async def get_catalyst_calendar(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve upcoming known catalysts: next earnings date, ex-dividend date, and scheduled earnings dates."""
    return await route_to_vendor("get_catalyst_calendar", ticker)


@tool
async def get_analyst_ratings(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve Wall Street analyst consensus: recommendation trend and price targets (low/mean/high)."""
    return await route_to_vendor("get_analyst_ratings", ticker)


@tool
async def get_short_interest(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve short-interest data: shares short, short ratio (days to cover), and short % of float."""
    return await route_to_vendor("get_short_interest", ticker)
