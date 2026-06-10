from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_institutional_holdings(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve institutional (13F) ownership, major-holder breakdown, and top mutual-fund holders for a company."""
    return await route_to_vendor("get_institutional_holdings", ticker)
