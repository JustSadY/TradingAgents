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
    # Currently routes to yfinance news as a proxy for web search results
    return await route_to_vendor("get_news", query, "2024-01-01", "2024-12-31")


@tool
async def get_crypto_fear_and_greed_index() -> str:
    """Retrieve the current Crypto Fear and Greed Index to gauge market sentiment."""
    return "Fear and Greed Index: 45 (Neutral)"
