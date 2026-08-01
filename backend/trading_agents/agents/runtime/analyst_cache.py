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
    await store_analyst_cache("my_analyst", ticker, data_hash, report_text)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.core.database import AsyncSessionLocal

_logger = logging.getLogger(__name__)

_CACHE_STALE_DAYS = 7

def _usable_report(value: object) -> str | None:
    """Return a non-blank report, or ``None`` for an invalid cache entry.

    A prior empty-model response could be persisted as whitespace.  Whitespace
    is truthy, so such an entry became a cache hit and kept the analyst panel
    visibly blank on every later run for that ticker.
    """
    if not isinstance(value, str):
        return None
    report = value.strip()
    return report or None

def _current_run_context() -> dict | None:
    try:
        from backend.trading_agents.agents.data.chart_tools import active_run_context

        return active_run_context.get(None)
    except Exception:
        return None

def _current_user_id() -> int | None:
    """The requesting user's id for the active run, or ``None`` for a
    system-triggered run with no owner. Cache lookups/writes always scope on
    this — never fall through to an unscoped query, which would let one
    user's cached report (and the report content it was built from) leak to
    another user."""
    ctx = _current_run_context()
    return ctx.get("user_id") if ctx else None

def _config_meta(analyst_key: str) -> dict:
    config_meta: dict = {}
    ctx = _current_run_context()
    if ctx and "graph" in ctx:
        graph = ctx["graph"]
        config_meta["global_provider"] = getattr(graph, "llm_provider", "") or ""
        config_meta["global_model"] = getattr(graph, "llm_model", "") or ""
        if hasattr(graph, "config") and isinstance(graph.config, dict):
            config_meta["persona"] = graph.config.get("investor_persona", "") or ""
            config_meta["language"] = graph.config.get("output_language", "") or ""

            runtime_agent_ctx = graph.config.get("runtime_agent_context", {})
            if isinstance(runtime_agent_ctx, dict):
                agent_ctx = runtime_agent_ctx.get(analyst_key, {})
                if isinstance(agent_ctx, dict):
                    agent_settings = agent_ctx.get("settings", {})
                    if isinstance(agent_settings, dict):
                        config_meta["agent_settings"] = agent_settings
    return config_meta

def _compute_config_fingerprint(analyst_key: str) -> str:
    """SHA-256 of just the provider/model/persona/language/agent-settings
    slice of the config — independent of the fetched data. Stored alongside
    each cache entry so the stale-data fallback (which ignores the full data
    hash by design) can still refuse to serve a report generated under a
    different model/persona/language."""
    import json

    try:
        config_meta = _config_meta(analyst_key)
    except Exception:
        config_meta = {}
    return hashlib.sha256(json.dumps(config_meta, sort_keys=True).encode("utf-8")).hexdigest()

def compute_data_hash(analyst_key: str, ticker: str, trade_date: str, *data_blocks: str) -> str:
    """Build a SHA-256 digest from the analyst key, ticker, trade date, and
    all fetched data blocks.  Any change in the underlying data produces a
    different hash, so the cached report is automatically invalidated."""
    try:
        config_meta = _config_meta(analyst_key)
    except Exception:
        config_meta = {}

    import json

    config_str = json.dumps(config_meta, sort_keys=True)
    combined = "|".join([analyst_key, ticker, trade_date, config_str, *(str(b) for b in data_blocks)])
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

async def check_analyst_cache(
    analyst_key: str,
    ticker: str,
    data_hash: str,
    *,
    fallback_to_stale: bool = True,
) -> str | None:
    """Return the cached report text if a matching entry exists.

    When *fallback_to_stale* is ``True`` (default) and no exact hash match is
    found, the most recent cache entry for this analyst+ticker is returned if
    it is younger than ``_CACHE_STALE_DAYS``.  This protects against transient
    data-fetch failures that change the hash but leave the underlying data
    effectively unchanged.
    """
    from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache

    user_id = _current_user_id()

    def _user_filter(col):
        return col.is_(None) if user_id is None else col == user_id

    async with AsyncSessionLocal() as db:
        if analyst_key == "news":
            stmt = (
                select(NewsAnalysisCache)
                .where(
                    _user_filter(NewsAnalysisCache.user_id),
                    NewsAnalysisCache.ticker == ticker,
                    NewsAnalysisCache.articles_hash == data_hash,
                )
                .order_by(NewsAnalysisCache.created_at.desc())
                .limit(10)
            )
        else:
            stmt = (
                select(AnalystReportCache)
                .where(
                    _user_filter(AnalystReportCache.user_id),
                    AnalystReportCache.analyst_key == analyst_key,
                    AnalystReportCache.ticker == ticker,
                    AnalystReportCache.data_hash == data_hash,
                )
                .order_by(AnalystReportCache.created_at.desc())
                .limit(10)
            )
        res = await db.execute(stmt)
        for entry in res.scalars():
            report = _usable_report(entry.analysis_result)
            if report is not None:
                return report
            _logger.warning(
                "Ignoring blank analyst cache entry id=%s for %s/%s.",
                getattr(entry, "id", "unknown"),
                analyst_key,
                ticker,
            )

        if not fallback_to_stale:
            return None

        config_fingerprint = _compute_config_fingerprint(analyst_key)
        cutoff = datetime.now(UTC) - timedelta(days=_CACHE_STALE_DAYS)
        if analyst_key == "news":
            stmt = (
                select(NewsAnalysisCache)
                .where(
                    _user_filter(NewsAnalysisCache.user_id),
                    NewsAnalysisCache.ticker == ticker,
                    NewsAnalysisCache.config_fingerprint == config_fingerprint,
                    NewsAnalysisCache.created_at >= cutoff,
                )
                .order_by(NewsAnalysisCache.created_at.desc())
                .limit(10)
            )
        else:
            stmt = (
                select(AnalystReportCache)
                .where(
                    _user_filter(AnalystReportCache.user_id),
                    AnalystReportCache.analyst_key == analyst_key,
                    AnalystReportCache.ticker == ticker,
                    AnalystReportCache.config_fingerprint == config_fingerprint,
                    AnalystReportCache.created_at >= cutoff,
                )
                .order_by(AnalystReportCache.created_at.desc())
                .limit(10)
            )
        res = await db.execute(stmt)
        for fallback in res.scalars():
            report = _usable_report(fallback.analysis_result)
            if report is None:
                _logger.warning(
                    "Ignoring blank stale analyst cache entry id=%s for %s/%s.",
                    getattr(fallback, "id", "unknown"),
                    analyst_key,
                    ticker,
                )
                continue
            _logger.info(
                "Stale-cache fallback for %s/%s (no exact hash match, using entry from %s)",
                analyst_key,
                ticker,
                fallback.created_at,
            )
            return report
    return None

async def store_analyst_cache(analyst_key: str, ticker: str, data_hash: str, report_text: str) -> None:
    """Persist a new cache entry so future runs with the same data can skip
    the LLM call."""
    from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache

    report = _usable_report(report_text)
    if report is None:
        _logger.warning("Not caching blank %s report for %s.", analyst_key, ticker)
        return

    user_id = _current_user_id()
    config_fingerprint = _compute_config_fingerprint(analyst_key)

    async with AsyncSessionLocal() as db:
        if analyst_key == "news":
            entry = NewsAnalysisCache(
                user_id=user_id,
                ticker=ticker,
                articles_hash=data_hash,
                config_fingerprint=config_fingerprint,
                analysis_result=report,
            )
        else:
            entry = AnalystReportCache(
                user_id=user_id,
                analyst_key=analyst_key,
                ticker=ticker,
                data_hash=data_hash,
                config_fingerprint=config_fingerprint,
                analysis_result=report,
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
    except Exception as _e:
        _logger.debug("emit_cache_hit skipped: %s", _e)
