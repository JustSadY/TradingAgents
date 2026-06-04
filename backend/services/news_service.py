"""News feed retrieval with a small in-process TTL cache.

Extracted from ``api/news.py`` so the route stays thin and the blocking
yfinance call is pushed to a worker thread instead of running on the event loop.
"""
from __future__ import annotations

import asyncio
import logging
import time

_logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_TTL_SECONDS = 900
_MAX_TICKERS = 10


def _fetch_news_sync(ticker: str) -> list[dict]:
    """Fetch (and cache) the parsed news list for a single ticker."""
    now = time.time()
    cached = _CACHE.get(ticker)
    if cached and now - cached[0] < _TTL_SECONDS:
        return cached[1]
    import yfinance as yf
    try:
        items = yf.Ticker(ticker).news or []
    except Exception as exc:
        _logger.debug("News fetch failed %s: %s", ticker, exc)
        return []
    parsed = []
    for n in items[:30]:
        content = n.get("content", {})
        title = content.get("title") or n.get("title", "")
        if not title:
            continue
        parsed.append({
            "ticker": ticker,
            "title": title,
            "summary": content.get("summary") or n.get("summary", ""),
            "url": (content.get("canonicalUrl") or {}).get("url") or n.get("link", ""),
            "published_at": str(content.get("pubDate") or n.get("providerPublishTime", "")),
            "source": (content.get("provider") or {}).get("displayName") or n.get("publisher", ""),
        })
    _CACHE[ticker] = (now, parsed)
    return parsed


async def get_news_feed(tickers: str, limit: int) -> list[dict]:
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:_MAX_TICKERS]

    def _work() -> list[dict]:
        collected: list[dict] = []
        for ticker in ticker_list:
            collected.extend(_fetch_news_sync(ticker)[:limit])
        collected.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return collected[: limit * len(ticker_list)]

    return await asyncio.to_thread(_work)
