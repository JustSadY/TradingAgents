from langchain_core.tools import tool
from typing import Annotated
from backend.trading_agents.dataflows.interface import route_to_vendor

@tool
def get_sec_filings(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """
    Retrieves the most recent SEC filings for a given company.
    Includes filing type (10-K, 10-Q, etc.), date, and title.
    """
    return route_to_vendor("get_sec_filings", ticker)

@tool
def get_insider_transactions_deep(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """
    Retrieves detailed insider trading transactions (Form 4).
    Essential for gauging management sentiment and conviction.
    """
    return route_to_vendor("get_insider_transactions", ticker)
