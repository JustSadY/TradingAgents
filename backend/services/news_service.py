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
_NEWS_FETCH_CONCURRENCY = 4


def _aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _normalize_tickers(tickers: str) -> list[str]:
    """Return up to the configured number of unique tickers in request order."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tickers.split(","):
        ticker = raw.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(ticker)
        if len(normalized) >= _MAX_TICKERS:
            break
    return normalized


async def _upsert_cache(db, ticker: str, parsed: list[dict], now: datetime) -> None:
    """Atomic cache write across PostgreSQL and SQLite."""
    from backend.models.news_cache import NewsCache

    values = {"ticker": ticker, "news_json": parsed, "updated_at": now}
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(NewsCache).values(**values).on_conflict_do_update(
            index_elements=[NewsCache.ticker],
            set_={"news_json": parsed, "updated_at": now},
        )
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(NewsCache).values(**values).on_conflict_do_update(
            index_elements=[NewsCache.ticker],
            set_={"news_json": parsed, "updated_at": now},
        )
    else:
        existing = await db.get(NewsCache, ticker)
        if existing:
            existing.news_json = parsed
            existing.updated_at = now
            return
        db.add(NewsCache(**values))
        return
    await db.execute(stmt)


def _fetch_news_sync(ticker: str) -> list[dict]:
    import yfinance as yf

    try:
        return yf.Ticker(ticker).news or []
    except Exception as exc:
        _logger.warning("News fetch failed %s: %s", ticker, exc)
        return []


def _parse_news_items(ticker: str, items: list[dict]) -> list[dict]:
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
    return parsed


async def _fetch_news_batch(tickers: list[str]) -> dict[str, list[dict]]:
    """Fetch cache misses concurrently without flooding the upstream provider."""
    semaphore = asyncio.Semaphore(_NEWS_FETCH_CONCURRENCY)

    async def _one(ticker: str) -> tuple[str, list[dict]]:
        async with semaphore:
            items = await asyncio.to_thread(_fetch_news_sync, ticker)
        return ticker, _parse_news_items(ticker, items)

    return dict(await asyncio.gather(*(_one(ticker) for ticker in tickers))) if tickers else {}


async def get_news_feed(tickers: str, limit: int) -> list[dict]:
    from sqlalchemy import select

    from backend.core.database import AsyncSessionLocal
    from backend.models.news_cache import NewsCache

    ticker_list = _normalize_tickers(tickers)
    if not ticker_list:
        return []

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=_TTL_SECONDS)

    # Read cached payloads into plain values and release the DB session before
    # any external yFinance calls. A slow upstream must not pin a DB connection
    # or keep a read transaction open for the duration of network I/O.
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(NewsCache).where(NewsCache.ticker.in_(ticker_list)))
        cache_map = {
            row.ticker: (_aware_utc(row.updated_at), list(row.news_json or []))
            for row in result.scalars().all()
        }

    resolved: dict[str, list[dict]] = {}
    missing: list[str] = []
    for ticker in ticker_list:
        cached = cache_map.get(ticker)
        if cached and cached[0] >= cutoff:
            resolved[ticker] = cached[1]
        else:
            missing.append(ticker)

    fetched = await _fetch_news_batch(missing)
    resolved.update(fetched)

    if fetched:
        async with AsyncSessionLocal() as db:
            for ticker, parsed in fetched.items():
                await _upsert_cache(db, ticker, parsed, now)
            await db.commit()

    collected: list[dict] = []
    for ticker in ticker_list:
        collected.extend(resolved.get(ticker, [])[:limit])

    collected.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return collected[: limit * len(ticker_list)]
