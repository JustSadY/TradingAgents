from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_macro_data(
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
) -> str:
    """Retrieve key numerical macroeconomic indicators (VIX, 10-Year Yield, Crude Oil, Gold, DXY) and global macro news."""
    indicators = await route_to_vendor("get_macro_data", curr_date)
    news = await route_to_vendor("get_global_news", curr_date, look_back_days=1, limit=5)
    return f"{indicators}\n\n## Global Macro News Flow\n{news}"
