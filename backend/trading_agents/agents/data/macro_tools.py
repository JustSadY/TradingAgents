from langchain_core.tools import tool
from typing import Annotated, Optional
from backend.trading_agents.dataflows.interface import route_to_vendor
@tool
async def get_macro_data(
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
) -> str:
    """Retrieve general macroeconomic indicators and market regime data (VIX, 10-Year Yield, Oil, Gold)."""
    # Note: Currently uses the global_news vendor for macro markers in some configurations
    return await route_to_vendor("get_global_news", curr_date, look_back_days=1, limit=10)
