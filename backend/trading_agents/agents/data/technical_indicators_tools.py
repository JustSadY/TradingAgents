import logging
from typing import Annotated

from langchain_core.tools import tool

from backend.trading_agents.dataflows.interface import route_to_vendor

_logger = logging.getLogger(__name__)


async def collect_indicators(
    symbol: str,
    indicators: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Fetch each requested technical indicator through the one-indicator vendor contract.

    Data vendors accept one indicator identifier at a time.  Keeping this
    fan-out outside the LangChain tool wrapper also lets the Market Analyst's
    prefetch path use exactly the same semantics as an LLM tool invocation.
    """
    indicator_list = [indicator.strip() for indicator in indicators.split(",") if indicator.strip()]
    if not indicator_list:
        return "No technical indicators requested."

    results = []
    for indicator in indicator_list:
        try:
            value = await route_to_vendor("get_indicators", symbol, indicator, curr_date, look_back_days)
            results.append(value)
        except Exception as exc:
            _logger.warning("Indicator %s failed for %s: %s", indicator, symbol, exc)
            results.append(f"Error calculating {indicator}: {exc}")
    return "\n\n".join(results)


@tool
async def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicators: Annotated[
        str,
        "Comma-separated technical indicators: 'close_50_sma', 'close_200_sma', 'close_10_ema', 'macd', 'macds', 'macdh', 'rsi', 'boll', 'boll_ub', 'boll_lb', 'atr', 'vwma', 'mfi'",
    ],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "How many days to look back for context"] = 30,
) -> str:
    """Calculate and retrieve specific technical indicators for a given stock symbol and time range."""
    return await collect_indicators(symbol, indicators, curr_date, look_back_days)
