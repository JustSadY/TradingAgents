from langchain_core.tools import tool
from typing import Annotated
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
async def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (YYYY-MM-DD)"] = None
) -> str:
    """Retrieve high-level company fundamentals (Sector, PE, Beta, Market Cap, etc.)."""
    return await route_to_vendor("get_fundamentals", ticker, curr_date)
@tool
async def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
) -> str:
    """Retrieve the company's balance sheet statement."""
    return await route_to_vendor("get_balance_sheet", ticker, freq, curr_date)
@tool
async def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
) -> str:
    """Retrieve the company's cash flow statement."""
    return await route_to_vendor("get_cashflow", ticker, freq, curr_date)
@tool
async def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
) -> str:
    """Retrieve the company's income statement."""
    return await route_to_vendor("get_income_statement", ticker, freq, curr_date)
