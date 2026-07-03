"""Shared cache helpers for analyst report caching.

Every analyst that produces a deterministic report from external data can
skip the (expensive) LLM call when the underlying data has not changed.

Usage in an analyst node::

    from backend.trading_agents.agents.runtime.analyst_cache import (
        check_analyst_cache, store_analyst_cache, compute_data_hash,
        emit_cache_hit,
    )

    data = await route_to_vendor(...)
    data_hash = compute_data_hash("my_analyst", ticker, trade_date, data)
    cached = await check_analyst_cache("my_analyst", ticker, data_hash)
    if cached:
        await emit_cache_hit("my_analyst", ticker)
        return {"messages": [AIMessage(content=cached)], "my_report": cached}
    # ... run LLM ...
    await store_analyst_cache("my_analyst", ticker, data_hash, report_text)
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import select

from backend.core.database import AsyncSessionLocal

_logger = logging.getLogger(__name__)


def compute_data_hash(analyst_key: str, ticker: str, trade_date: str, *data_blocks: str) -> str:
    """Build a SHA-256 digest from the analyst key, ticker, trade date, and
    all fetched data blocks.  Any change in the underlying data produces a
    different hash, so the cached report is automatically invalidated."""
    combined = "|".join([analyst_key, ticker, trade_date, *(str(b) for b in data_blocks)])
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


async def check_analyst_cache(analyst_key: str, ticker: str, data_hash: str) -> str | None:
    """Return the cached report text if a matching entry exists, else ``None``."""
    from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache

    async with AsyncSessionLocal() as db:
        # News analyst uses its own table (NewsAnalysisCache)
        if analyst_key == "news":
            stmt = select(NewsAnalysisCache).where(
                NewsAnalysisCache.ticker == ticker,
                NewsAnalysisCache.articles_hash == data_hash,
            )
        else:
            stmt = select(AnalystReportCache).where(
                AnalystReportCache.analyst_key == analyst_key,
                AnalystReportCache.ticker == ticker,
                AnalystReportCache.data_hash == data_hash,
            )
        res = await db.execute(stmt)
        entry = res.scalar_one_or_none()
        if entry:
            return entry.analysis_result
    return None


async def store_analyst_cache(analyst_key: str, ticker: str, data_hash: str, report_text: str) -> None:
    """Persist a new cache entry so future runs with the same data can skip
    the LLM call."""
    from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache

    async with AsyncSessionLocal() as db:
        if analyst_key == "news":
            entry = NewsAnalysisCache(
                ticker=ticker,
                articles_hash=data_hash,
                analysis_result=report_text,
            )
        else:
            entry = AnalystReportCache(
                analyst_key=analyst_key,
                ticker=ticker,
                data_hash=data_hash,
                analysis_result=report_text,
            )
        db.add(entry)
        await db.commit()


async def emit_cache_hit(analyst_key: str, ticker: str) -> None:
    """Emit a mental-model event telling the user that the cached report is
    being reused (token savings)."""
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        ctx = active_run_context.get(None)
        if ctx and "emitter" in ctx:
            emitter = ctx["emitter"]
            await emitter.emit_mental_model(
                analyst_key,
                f"Reusing cached {analyst_key} analysis for {ticker} (saved tokens).",
            )
    except Exception:
        pass  # Never fail the run over a cosmetic notification
""",
<parameter name="Description">Shared cache helper that all analysts will use instead of duplicating cache logic inline. Provides compute_data_hash, check_analyst_cache, store_analyst_cache, and emit_cache_hit functions.
