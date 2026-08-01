"""News feed retrieval with a centralized database-backed TTL cache.

Shared across multiple uvicorn worker processes safely.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

_logger = logging.getLogger(__name__)

_TTL_SECONDS = 900
_MAX_TICKERS = 10

def _fetch_news_sync(ticker: str) -> list[dict]:
    import yfinance as yf

    try:
        return yf.Ticker(ticker).news or []
    except Exception as exc:
        _logger.warning("News fetch failed %s: %s", ticker, exc)
        return []

async def get_news_feed(tickers: str, limit: int) -> list[dict]:
    from sqlalchemy import select

    from backend.core.database import AsyncSessionLocal
    from backend.models.news_cache import NewsCache

    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()][:_MAX_TICKERS]
    collected: list[dict] = []

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=_TTL_SECONDS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(NewsCache).where(NewsCache.ticker.in_(ticker_list)))
        cache_map = {row.ticker: row for row in result.scalars().all()}

        for ticker in ticker_list:
            cached = cache_map.get(ticker)
            if cached and cached.updated_at >= cutoff:
                collected.extend(cached.news_json[:limit])
            else:
                items = await asyncio.to_thread(_fetch_news_sync, ticker)

                parsed = []
                for n in items[:30]:
                    content = n.get("content", {})
                    title = content.get("title") or n.get("title", "")
                    if not title:
                        continue
                    parsed.append(
                        {
                            "ticker": ticker,
                            "title": title,
                            "summary": content.get("summary") or n.get("summary", ""),
                            "url": (content.get("canonicalUrl") or {}).get("url") or n.get("link", ""),
                            "published_at": str(content.get("pubDate") or n.get("providerPublishTime", "")),
                            "source": (content.get("provider") or {}).get("displayName") or n.get("publisher", ""),
                        }
                    )

                if cached:
                    cached.news_json = parsed
                    cached.updated_at = now
                else:
                    cached = NewsCache(ticker=ticker, news_json=parsed, updated_at=now)
                    db.add(cached)

                collected.extend(parsed[:limit])

        await db.commit()

    collected.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return collected[: limit * len(ticker_list)]
