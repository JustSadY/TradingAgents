from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

@tool
async def get_sec_filings(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve recent SEC filings (10-K, 10-Q, 8-K) for a company to analyze corporate strategy and risks."""
    return await route_to_vendor("get_sec_filings", ticker)

@tool
async def get_insider_transactions_deep(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve detailed insider transaction logs for a company to analyze management sentiment."""
    return await route_to_vendor("get_insider_transactions", ticker)
