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
    import asyncio

    from backend.trading_agents.dataflows.config import get_config
    from backend.trading_agents.dataflows.searxng import fetch_searxng_results

    searxng_url = (get_config().get("searxng_url") or "").strip()
    if searxng_url:
        try:
            return await asyncio.to_thread(fetch_searxng_results, query, searxng_url)
        except Exception as exc:
            _logger.warning("SearXNG query failed (%s); falling back to news proxy: %s", searxng_url, exc)

    from datetime import UTC, datetime, timedelta

    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        trade_date_str = ctx.get("trade_date") if ctx else None
    except Exception:
        trade_date_str = None

    end_dt = datetime.now(UTC)
    if trade_date_str:
        try:
            end_dt = datetime.strptime(trade_date_str, "%Y-%m-%d")
        except ValueError:
            pass

    start_date = (end_dt - timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    ticker_candidate = query.split()[0].strip() if query and query.strip() else query
    try:
        return await route_to_vendor("get_news", ticker_candidate, start_date, end_date)
    except Exception as vendor_exc:
        _logger.warning("News proxy fallback failed for query %r (candidate %r): %s", query, ticker_candidate, vendor_exc)
        return f"Web search and news fallback unavailable for query: {query}"

@tool
async def get_crypto_fear_and_greed_index() -> str:
    """Retrieve the current Crypto Fear and Greed Index to gauge market sentiment."""
    import asyncio

    from backend.trading_agents.dataflows.crypto_fear_greed import fetch_crypto_fear_greed_index

    return await asyncio.to_thread(fetch_crypto_fear_greed_index)
