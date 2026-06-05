from langchain_core.tools import tool
from typing import Annotated, Optional
import logging
from backend.trading_agents.dataflows.interface import route_to_vendor
_logger = logging.getLogger(__name__)
@tool
async def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicators: Annotated[str, "Comma-separated technical indicators: 'close_50_sma', 'close_200_sma', 'close_10_ema', 'macd', 'macds', 'macdh', 'rsi', 'boll', 'boll_ub', 'boll_lb', 'atr', 'vwma', 'mfi'"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "How many days to look back for context"] = 30,
) -> str:
    """Calculate and retrieve specific technical indicators for a given stock symbol and time range."""
    indicator_list = [i.strip() for i in indicators.split(",") if i.strip()]
    results = []
    for ind in indicator_list:
        try:
            val = await route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days)
            results.append(val)
        except Exception as e:
            _logger.error("Indicator %s failed for %s: %s", ind, symbol, e)
            results.append(f"Error calculating {ind}: {e}")
    return "\n\n".join(results)
