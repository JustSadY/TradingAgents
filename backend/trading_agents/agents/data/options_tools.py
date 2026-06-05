from langchain_core.tools import tool
from typing import Annotated
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
async def get_options_data(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Retrieve options chain data, including Put/Call ratios and Implied Volatility (IV) metrics."""
    # Placeholder: currently routes to a news-based sentiment summary if no direct options vendor is set
    return await route_to_vendor("get_news", symbol, "2024-01-01", "2024-12-31")
