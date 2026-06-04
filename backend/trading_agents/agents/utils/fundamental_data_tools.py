from langchain_core.tools import tool
from typing import Annotated
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve key fundamental metrics (P/E ratio, market cap, EPS, etc.) for a company."""
    return route_to_vendor("get_fundamentals", ticker, curr_date)
@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve the balance sheet statements for a given ticker symbol and frequency."""
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)
@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve the cash flow statements for a given ticker symbol and frequency."""
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)
@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve the income statement report for a given ticker symbol and frequency."""
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)
