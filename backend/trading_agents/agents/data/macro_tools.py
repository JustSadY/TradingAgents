from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor


@tool
async def get_macro_data(
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"],
) -> str:
    """Retrieve recent global macro news used as a market-regime proxy.

    Note: no dedicated market-data vendor (VIX, 10-Year Yield, Oil, Gold) is
    wired up, so this returns recent global macro news rather than those
    numeric markers. Do not fabricate specific index/yield values from it.
    """
    return await route_to_vendor("get_global_news", curr_date, look_back_days=1, limit=10)
