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
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.core.rls_context import set_user_background_context

_logger = logging.getLogger(__name__)

_CACHE_STALE_DAYS = 7

@asynccontextmanager
async def _cache_session(user_id: int):
    """Open a cache session already scoped to the run's owner.

    PostgreSQL row-level security evaluates every statement against the
    ``app.*`` settings of the current transaction. A session opened without a
    context therefore turns each lookup into a silent miss and each insert into
    an ``InsufficientPrivilegeError`` that fails the whole analyst node. Tests
    build SQLite from ORM metadata and have no RLS, which is why this only ever
    surfaced against PostgreSQL.
    """

    async with AsyncSessionLocal() as db:
        await set_user_background_context(db, user_id)
        yield db


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



def _current_trade_date() -> str | None:
    ctx = _current_run_context()
    value = ctx.get("trade_date") if ctx else None
    return str(value) if value else None


def _current_temporal_mode() -> str:
    ctx = _current_run_context()
    return "historical" if ctx and ctx.get("historical_mode") else "live"


def _record_cache_hit(*, stale: bool, created_at=None) -> None:
    ctx = _current_run_context()
    if ctx is not None:
        ctx["last_analyst_cache_hit"] = {
            "stale": stale,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
            "trade_date": _current_trade_date(),
            "temporal_mode": _current_temporal_mode(),
        }

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
        # The planner runs immediately before analysts and stores only a hash
        # here.  It changes both exact data-cache hashes and stale-fallback
        # fingerprints, so a cached report generated for yesterday's agenda
        # cannot silently bypass a new assumption/invalidation test.
        plan_key = ctx.get("analysis_plan_cache_key")
        if isinstance(plan_key, str) and plan_key:
            config_meta["analysis_plan_cache_key"] = plan_key
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
    """Look the report up, treating any lookup failure as a cache miss.

    A miss costs an LLM call; a raised exception costs the analyst its report,
    because the node reports the exception in place of one.
    """

    try:
        return await _lookup_analyst_cache(
            analyst_key, ticker, data_hash, fallback_to_stale=fallback_to_stale
        )
    except Exception as exc:  # noqa: BLE001 — caching is an optimisation, not the result
        _logger.warning("Failed to read the %s cache for %s: %s", analyst_key, ticker, exc)
        return None


async def _lookup_analyst_cache(
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
    if user_id is None:
        # An ownerless run has no tenant to scope the cache to, and rows with a
        # NULL owner are unreachable under the tenant policy anyway.
        return None
    trade_date = _current_trade_date()
    temporal_mode = _current_temporal_mode()
    if temporal_mode == "historical":
        # Exact hashes include the date.  Stale fallback is deliberately
        # disabled because a transient fetch failure must not substitute a
        # report produced with a different point-in-time evidence set.
        fallback_to_stale = False

    def _user_filter(col):
        return col == user_id

    async with _cache_session(user_id) as db:
        if analyst_key == "news":
            stmt = (
                select(NewsAnalysisCache)
                .where(
                    _user_filter(NewsAnalysisCache.user_id),
                    NewsAnalysisCache.ticker == ticker,
                    NewsAnalysisCache.trade_date == trade_date,
                    NewsAnalysisCache.temporal_mode == temporal_mode,
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
                    AnalystReportCache.trade_date == trade_date,
                    AnalystReportCache.temporal_mode == temporal_mode,
                    AnalystReportCache.data_hash == data_hash,
                )
                .order_by(AnalystReportCache.created_at.desc())
                .limit(10)
            )
        res = await db.execute(stmt)
        for entry in res.scalars():
            report = _usable_report(entry.analysis_result)
            if report is not None:
                _record_cache_hit(stale=False, created_at=getattr(entry, "created_at", None))
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
                    NewsAnalysisCache.trade_date == trade_date,
                    NewsAnalysisCache.temporal_mode == temporal_mode,
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
                    AnalystReportCache.trade_date == trade_date,
                    AnalystReportCache.temporal_mode == temporal_mode,
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
            _record_cache_hit(stale=True, created_at=getattr(fallback, "created_at", None))
            return report
    return None

async def store_analyst_cache(analyst_key: str, ticker: str, data_hash: str, report_text: str) -> None:
    """Persist a new cache entry so future runs with the same data can skip
    the LLM call.

    Memoisation only: the report has already been produced by the time this
    runs, so a persistence failure is logged and swallowed. Letting it
    propagate failed the analyst node *after* a good report existed, and the
    user get the raised database error as the report body.
    """
    report = _usable_report(report_text)
    if report is None:
        _logger.warning("Not caching blank %s report for %s.", analyst_key, ticker)
        return

    user_id = _current_user_id()
    if user_id is None:
        _logger.debug("Skipping %s cache write for %s: the run has no owner.", analyst_key, ticker)
        return
    trade_date = _current_trade_date()
    temporal_mode = _current_temporal_mode()
    config_fingerprint = _compute_config_fingerprint(analyst_key)

    try:
        await _write_cache_entry(
            analyst_key,
            ticker,
            data_hash,
            report,
            user_id=user_id,
            trade_date=trade_date,
            temporal_mode=temporal_mode,
            config_fingerprint=config_fingerprint,
        )
    except Exception as exc:  # noqa: BLE001 — caching is an optimisation, not the result
        _logger.warning("Failed to cache the %s report for %s: %s", analyst_key, ticker, exc)


async def _write_cache_entry(
    analyst_key: str,
    ticker: str,
    data_hash: str,
    report: str,
    *,
    user_id: int,
    trade_date: str | None,
    temporal_mode: str,
    config_fingerprint: str,
) -> None:
    from backend.models.news_cache import AnalystReportCache, NewsAnalysisCache

    async with _cache_session(user_id) as db:
        if analyst_key == "news":
            entry = NewsAnalysisCache(
                user_id=user_id,
                ticker=ticker,
                trade_date=trade_date,
                temporal_mode=temporal_mode,
                articles_hash=data_hash,
                config_fingerprint=config_fingerprint,
                analysis_result=report,
            )
        else:
            entry = AnalystReportCache(
                user_id=user_id,
                analyst_key=analyst_key,
                ticker=ticker,
                trade_date=trade_date,
                temporal_mode=temporal_mode,
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
            meta = ctx.get("last_analyst_cache_hit") or {}
            age = f" generated {meta.get('created_at')}" if meta.get("created_at") else ""
            freshness = "stale fallback" if meta.get("stale") else "exact cache hit"
            date_note = f" for trade date {meta.get('trade_date')}" if meta.get("trade_date") else ""
            await emitter.emit_mental_model(
                analyst_key,
                f"Reusing {freshness}{date_note}{age} for {ticker} (saved tokens).",
            )
    except Exception as _e:
        _logger.debug("emit_cache_hit skipped: %s", _e)
