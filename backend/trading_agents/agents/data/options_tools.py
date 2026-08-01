from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

@tool
async def get_options_data(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Retrieve live options chain summary metrics, including Put/Call ratios, Implied Volatility (IV), and Open Interest."""
    return await route_to_vendor("get_options_data", symbol)
