import asyncio
from typing import Awaitable
import json as _json
import logging
import os as _os
import tempfile
import time
import uuid

import backend.bootstrap  # noqa: F401  (sets engine env before importing the engine)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AsyncSessionLocal
from backend.core.websocket import ws_manager
from backend.core.catalog import node_progress
from backend.core.config import get_settings as _cfg
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.repositories.analysis import (
    get_analysis_by_id,
    get_system_settings,
    list_historical_analyses,
)
from backend.services.settings_service import get_or_create_settings
from backend.services.stats_handler import StatsCallbackHandler
from backend.services.performance_service import get_analyst_attribution_stats
from backend.services.tool_settings_service import build_global_runtime_context
from backend.services.tool_access_service import get_user_agent_access
from backend.services.agent_settings_service import build_agent_runtime_context
from backend.services.user_service import get_user_api_key, decrypt_api_keys
from backend.services.notification_service import notify_analysis_complete
from backend.services.annotation_service import extract_chart_annotations
from backend.services.trading_orchestrator import place_signal_order

# Heavy graph node / schemas imports:
from backend.trading_agents.graph.trading_graph import TradingAgentsGraph
from backend.trading_agents.default_config import DEFAULT_CONFIG
from backend.trading_agents.agents.schemas import PropagateResult
from backend.trading_agents.agents.sub.managers.super_portfolio_manager import create_super_portfolio_manager

_logger = logging.getLogger(__name__)
_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_TASK_REGISTRY: dict[str, dict] = {}  # task_id -> {ticker, date, user_id, started_at, ...}
_BACKGROUND_TASKS: set[asyncio.Task] = set()
_ANALYSIS_BACKGROUND_TASKS: dict[str, set[asyncio.Task]] = {}
_REPORT_FIELDS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "macro_report", "options_report", "quant_report", "earnings_report",
    "review_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
)


async def _get_historical_analyses_context(
    ticker: str, trade_date: str, db: AsyncSession, limit: int = 5, output_language: str = "English"
) -> str:
    from sqlalchemy import select, desc
    from backend.models.analysis import AnalysisResult
    
    # 1. Fetch same-ticker historical analyses
    q_same = (
        select(AnalysisResult)
        .where(AnalysisResult.ticker == ticker)
        .where(AnalysisResult.trade_date < trade_date)
        .order_by(desc(AnalysisResult.created_at))
        .limit(limit)
    )
    res_same = await db.execute(q_same)
    rows_same = res_same.scalars().all()
    
    # 2. Fetch cross-ticker lessons (those with populated reflection)
    q_cross = (
        select(AnalysisResult)
        .where(AnalysisResult.ticker != ticker)
        .where(AnalysisResult.reflection != "")
        .order_by(desc(AnalysisResult.created_at))
        .limit(3)
    )
    res_cross = await db.execute(q_cross)
    rows_cross = res_cross.scalars().all()

    if not rows_same and not rows_cross:
        return ""

    from backend.core.l10n import get_message
    parts = []
    
    if rows_same:
        parts.append(get_message("historical_reports_title", output_language, ticker=ticker))
        for row in reversed(rows_same):
            date_label = get_message("date_signal_label", output_language, date=row.trade_date)
            parts.append(f"--- {date_label}: {row.signal or 'N/A'} ---")
            parts.append(f"Final Decision:\n{row.final_decision}")
            if row.reflection:
                parts.append(f"Reflection/Outcome:\n{row.reflection}")
            parts.append("")

    if rows_cross:
        parts.append(get_message("cross_ticker_lessons_title", output_language))
        for row in rows_cross:
            parts.append(f"--- Ticker: {row.ticker} | Date: {row.trade_date} ---")
            parts.append(f"Reflection:\n{row.reflection}")
            parts.append("")

    return "\n".join(parts)


def _inject_tool_credentials(config: dict) -> None:
    runtime_tool_context = config.get("runtime_tool_context")
    if not runtime_tool_context:
        return
    user_settings = runtime_tool_context.get("user_settings", {})
    server_settings = runtime_tool_context.get("server_settings", {})
    
    # reddit_sentiment settings (strictly user scope)
    reddit_user = user_settings.get("reddit_sentiment", {}).get("settings", {})
    config["reddit_client_id"] = reddit_user.get("reddit_client_id")
    config["reddit_client_secret"] = reddit_user.get("reddit_client_secret")
    config["reddit_user_agent"] = reddit_user.get("reddit_user_agent")
    
    # search_web settings (strictly user scope)
    search_user = user_settings.get("search_web", {}).get("settings", {})
    config["searxng_url"] = search_user.get("searxng_url")
    
    # core_stock_data settings (server scope)
    stock_server = server_settings.get("core_stock_data", {}).get("settings", {})
    config["alpha_vantage_api_key"] = stock_server.get("alpha_vantage_api_key")


def _build_config(settings: AppSettings, user=None, sys_settings=None) -> dict:
    # Data-vendor routing is a server-level concern: read it from the global
    # SystemSettings (falling back to its active_data_vendor / yfinance), not
    # from per-user app settings.
    _vendor_default = getattr(sys_settings, "active_data_vendor", None) or "yfinance"

    def _vendor(field: str) -> str:
        return getattr(sys_settings, field, None) or _vendor_default

    cfg: dict = {
        "data_cache_dir": _os.environ.get("TRADINGAGENTS_DATA_CACHE_DIR", DEFAULT_CONFIG["data_cache_dir"]),
        "results_dir":    _os.environ.get("TRADINGAGENTS_RESULTS_DIR", DEFAULT_CONFIG["results_dir"]),
        "memory_log_path": _os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH", DEFAULT_CONFIG["memory_log_path"]),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": settings.output_language or DEFAULT_CONFIG["output_language"],
        "investor_persona": settings.investor_persona or DEFAULT_CONFIG["investor_persona"],
        "analyst_concurrency_limit": settings.analyst_concurrency_limit or DEFAULT_CONFIG["analyst_concurrency_limit"],
        "skip_disk_log": True,
        # Checkpoint (resume) is always enabled — no longer a user/admin setting.
        "checkpoint_enabled": True,
        "node_retry_attempts": getattr(settings, "node_retry_attempts", DEFAULT_CONFIG["node_retry_attempts"]) or DEFAULT_CONFIG["node_retry_attempts"],
        "node_retry_base_delay": getattr(settings, "node_retry_base_delay", DEFAULT_CONFIG["node_retry_base_delay"]) or DEFAULT_CONFIG["node_retry_base_delay"],
        "strict_backtest_learning": getattr(settings, "strict_backtest_learning", DEFAULT_CONFIG["strict_backtest_learning"]) if getattr(settings, "strict_backtest_learning", None) is not None else DEFAULT_CONFIG["strict_backtest_learning"],
        "max_recur_limit": getattr(settings, "max_recur_limit", DEFAULT_CONFIG["max_recur_limit"]) or DEFAULT_CONFIG["max_recur_limit"],
        "news_article_limit": getattr(settings, "news_article_limit", DEFAULT_CONFIG["news_article_limit"]) or DEFAULT_CONFIG["news_article_limit"],
        "global_news_article_limit": getattr(settings, "global_news_article_limit", DEFAULT_CONFIG["global_news_article_limit"]) or DEFAULT_CONFIG["global_news_article_limit"],
        "global_news_lookback_days": getattr(settings, "global_news_lookback_days", DEFAULT_CONFIG["global_news_lookback_days"]) or DEFAULT_CONFIG["global_news_lookback_days"],
        "data_vendors": {
            "core_stock_apis": _vendor("data_vendor_core_stock"),
            "technical_indicators": _vendor("data_vendor_technicals"),
            "fundamental_data": _vendor("data_vendor_fundamentals"),
            "news_data": _vendor("data_vendor_news"),
        },
        "is_admin": getattr(user, "is_admin", False) if user is not None else False,
        "has_user": user is not None,
    }
    if getattr(settings, "benchmark_ticker", None):
        cfg["benchmark_ticker"] = settings.benchmark_ticker

    if user is not None:
        try:
            fernet = _cfg().get_fernet()
            current_provider = cfg.get("llm_provider", "openai")
            user_key = get_user_api_key(user, current_provider, fernet)
            if user.api_keys_enc:
                cfg["user_api_keys"] = decrypt_api_keys(user.api_keys_enc, fernet)
            else:
                cfg["user_api_keys"] = {}
        except Exception as e:
            _logger.error("Failed to decrypt user API keys in _build_config: %s", e)
            user_key = None
            cfg["user_api_keys"] = {}
        if user_key:
            cfg["api_key"] = user_key
    return cfg


def _history_json_from(value):
    if not value:
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        val_s = value.strip()
        if (val_s.startswith("[") and val_s.endswith("]")) or (val_s.startswith("{") and val_s.endswith("}")):
            try:
                return _json.loads(val_s)
            except Exception as e:
                _logger.debug("Failed parsing history JSON string: %s", e)
    return value


def _extract_stats(handler) -> dict:
    try:
        return handler.get_stats()
    except Exception as e:
        _logger.warning("Failed to extract stats from handler: %s", e)
        return {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}


async def cancel_analysis(task_id: str) -> bool:
    task = _RUNNING_TASKS.pop(task_id, None)
    _TASK_REGISTRY.pop(task_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def get_active_tasks_for_user(user_id: int | None) -> list[dict]:
    """Returns a list of active tasks for the given user."""
    return [
        {"task_id": tid, **meta}
        for tid, meta in _TASK_REGISTRY.items()
        if meta.get("user_id") == user_id
    ]


def _track_background_task(coro: Awaitable[None], task_id: str | None = None):
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    if task_id:
        tasks = _ANALYSIS_BACKGROUND_TASKS.setdefault(task_id, set())
        tasks.add(task)

    def _cleanup(done_task: asyncio.Task) -> None:
        _BACKGROUND_TASKS.discard(done_task)
        if task_id and task_id in _ANALYSIS_BACKGROUND_TASKS:
            scoped = _ANALYSIS_BACKGROUND_TASKS[task_id]
            scoped.discard(done_task)
            if not scoped:
                _ANALYSIS_BACKGROUND_TASKS.pop(task_id, None)

    task.add_done_callback(_cleanup)
    return task


async def _await_analysis_background_tasks(task_id: str) -> None:
    pending = list(_ANALYSIS_BACKGROUND_TASKS.get(task_id, set()))
    if not pending:
        return
    await asyncio.gather(*pending, return_exceptions=True)


async def _send_analysis_webhook(ticker, trade_date, signal, final_decision, settings):
    try:
        await notify_analysis_complete(ticker, signal, trade_date, final_decision, settings)
    except Exception as exc:
        _logger.debug("Webhook notify failed (non-fatal): %s", exc)


async def _extract_and_save_annotations(
    analysis_id: int,
    market_report: str,
    final_decision: str,
    quick_llm,
    custom_indicators: list = None,
    visual_annotations: list = None,
    output_language: str = "English",
) -> None:
    try:
        annotations = await extract_chart_annotations(market_report, final_decision, quick_llm, output_language=output_language)
        if not annotations:
            annotations = {}
        if custom_indicators:
            annotations["custom_indicators"] = custom_indicators
        if visual_annotations:
            annotations["annotations"] = visual_annotations
        if not annotations:
            return
        async with AsyncSessionLocal() as s:
            row = await get_analysis_by_id(s, analysis_id)
            if row:
                row.chart_annotations = annotations
                await s.commit()
    except Exception as exc:
        _logger.debug("Annotation save failed (non-fatal): %s", exc)


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    task_id: str | None = None,
    user=None,
) -> tuple[str, AnalysisResult]:
    if user is not None:
        settings = await get_or_create_settings(db, user)
    if task_id is None:
        task_id = str(uuid.uuid4())
    current = asyncio.current_task()
    if current:
        _RUNNING_TASKS[task_id] = current
        _TASK_REGISTRY[task_id] = {
            "ticker": ticker,
            "trade_date": trade_date,
            "asset_type": asset_type,
            "user_id": user.id if user else None,
            "started_at": time.time(),
            "status": "running"
        }
    username = user.username if user else "system"
    _logger.info("Starting analysis task=%s ticker=%s date=%s user=%s", task_id, ticker, trade_date, username)
    await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "Initializing"})
    loop = asyncio.get_running_loop()

    def _emit(event: dict) -> None:
        try:
            asyncio.run_coroutine_threadsafe(ws_manager.send(task_id, event), loop)
        except Exception:
            pass

    stats_handler = StatsCallbackHandler()
    start = time.time()
    try:
        sys_settings = await get_system_settings(db)
        await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "Preparing LLM client..."})
        config = _build_config(settings, user=user, sys_settings=sys_settings)
        attribution_md = ""
        try:
            attribution_data = await get_analyst_attribution_stats(db)
            if attribution_data.get("attribution"):
                attribution_md = "=== ANALYST PERFORMANCE ATTRIBUTION & WEIGHTS ===\n"
                attribution_md += "Below are the historical win rates and normalized voting weights assigned to each analyst based on empirical accuracy:\n"
                for att in attribution_data["attribution"]:
                    attribution_md += f"- {att['label']}: Win Rate = {att['win_rate']}%, Assigned Weight = {att['weight']}%\n"
                attribution_md += "\n[IMPORTANT] During decision synthesis, discount opinions of analysts with lower weights and heavily prioritize opinions of analysts with higher weights.\n\n"
        except Exception as _attr_exc:
            _logger.warning("Could not load analyst attribution stats (skipping): %s", _attr_exc)
        hist_ctx = ""
        if getattr(settings, "include_historical_analyses", False):
            limit = getattr(settings, "historical_analyses_limit", 5) or 5
            db_ctx = await _get_historical_analyses_context(
                ticker, trade_date, db, limit=limit, output_language=settings.output_language
            )
            if db_ctx:
                hist_ctx = db_ctx
        config["historical_context"] = attribution_md + hist_ctx

        user_id = user.id if user else None
        agent_access_map = {}
        if user_id is not None:
            agent_access_map = await get_user_agent_access(db, user_id)
        
        from backend.trading_agents.agent_catalog import list_analysts
        all_analyst_keys = [a.key for a in list_analysts()]
        permitted_analysts = [
            a for a in all_analyst_keys
            if agent_access_map.get(a, True)
        ]
        runtime_tool_context = await build_global_runtime_context(db, user_id)
        config["runtime_tool_context"] = runtime_tool_context
        _inject_tool_credentials(config)

        config["runtime_agent_context"] = await build_agent_runtime_context(db, user_id)

        ta = TradingAgentsGraph(
            selected_analysts=permitted_analysts,
            debug=False,
            config=config,
            callbacks=[stats_handler],
        )

        prev_state: dict = {}
        prev_inv_count = 0
        prev_risk_count = 0
        last_node = None

        async def _stream_observer(mode: str, chunk: dict) -> None:
            nonlocal prev_inv_count, prev_risk_count, last_node
            if mode == "updates":
                for node_name in (chunk or {}):
                    if node_name != last_node:
                        prog = node_progress(node_name)
                        if prog:
                            _emit(prog)
                            last_node = node_name
                return
            inv_state = chunk.get("investment_debate_state") or {}
            if inv_state and inv_state.get("count", 0) > prev_inv_count:
                prev_inv_count = inv_state.get("count", 0)
                history = inv_state.get("history", "")
                lines = [line.strip() for line in history.split("\n") if line.strip()]
                if lines:
                    _emit({"type": "debate_bubble", "debate_type": "investment", "message": lines[-1]})
            risk_state = chunk.get("risk_debate_state") or {}
            if risk_state and risk_state.get("count", 0) > prev_risk_count:
                prev_risk_count = risk_state.get("count", 0)
                history = risk_state.get("history", "")
                lines = [line.strip() for line in history.split("\n") if line.strip()]
                if lines:
                    _emit({"type": "debate_bubble", "debate_type": "risk", "message": lines[-1]})
            for key, value in chunk.items():
                if key in _REPORT_FIELDS and value and value != prev_state.get(key):
                    _emit({"type": "report", "section": key, "content": value})
                    prev_state[key] = value

        final_state, signal = await ta.async_propagate(
            ticker,
            trade_date,
            asset_type,
            stream_observer=_stream_observer,
        )
        stats = _extract_stats(stats_handler)
        duration = time.time() - start
        result = PropagateResult.from_state(final_state, signal)
        inv_debate = final_state.get("investment_debate_state", {}) or {}
        risk_debate = final_state.get("risk_debate_state", {}) or {}
        row = AnalysisResult(
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            signal=result.signal,
            market_report=result.market_report,
            sentiment_report=result.sentiment_report,
            news_report=result.news_report,
            fundamentals_report=result.fundamentals_report,
            macro_report=result.macro_report,
            options_report=result.options_report,
            quant_report=result.quant_report,
            earnings_report=result.earnings_report,
            review_report=result.review_report,
            investment_plan=result.investment_plan,
            trader_plan=result.trader_plan,
            final_decision=result.final_decision,
            bull_history=_history_json_from(inv_debate.get("bull_history", "")),
            bear_history=_history_json_from(inv_debate.get("bear_history", "")),
            investment_debate_history=_history_json_from(inv_debate.get("history", "")),
            risk_debate_history=_history_json_from(risk_debate.get("history", "")),
            judge_decision=str(inv_debate.get("judge_decision", "") or ""),
            llm_calls=stats.get("llm_calls", 0),
            tool_calls=stats.get("tool_calls", 0),
            tokens_in=stats.get("tokens_in", 0),
            tokens_out=stats.get("tokens_out", 0),
            duration_seconds=duration,
            triggered_by=triggered_by,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            preset_name=settings.active_preset_name or f"{settings.llm_provider}:{settings.llm_model}",
        )
        db.add(row)
        await db.flush()
        _track_background_task(_extract_and_save_annotations(
            row.id, 
            result.market_report, 
            result.final_decision, 
            ta.thinking_llm,
            getattr(ta, "custom_indicators", []),
            getattr(ta, "visual_annotations", []),
            output_language=settings.output_language
        ), task_id=task_id)
        _track_background_task(_send_analysis_webhook(
            ticker, trade_date, signal, result.final_decision, settings
        ), task_id=task_id)
        await _await_analysis_background_tasks(task_id)
        await ws_manager.send(task_id, {
            "type": "decision",
            "signal": signal,
            "final_decision": result.final_decision,
        })
        await ws_manager.send(task_id, {
            "type": "complete",
            "analysis_id": row.id,
            "signal": signal,
            "duration_seconds": round(duration, 2),
            "llm_calls": stats.get("llm_calls", 0),
        })
        _logger.info("Analysis complete task=%s ticker=%s signal=%s user=%s duration=%.2fs", task_id, ticker, signal, username, duration)
        return task_id, row
    except asyncio.CancelledError:
        _logger.info("Analysis cancelled task=%s user=%s", task_id, username)
        await ws_manager.send(task_id, {"type": "error", "message": "Analysis cancelled."})
        raise
    except Exception as exc:
        _logger.error("Analysis failed task=%s user=%s: %s", task_id, username, exc, exc_info=True)
        await ws_manager.send(task_id, {"type": "error", "message": str(exc)})
        raise
    finally:
        _RUNNING_TASKS.pop(task_id, None)
        _TASK_REGISTRY.pop(task_id, None)
        await ws_manager.close_task(task_id)


async def run_portfolio_analysis(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    user=None,
):
    username = user.username if user else "system"
    _logger.info("Starting portfolio analysis for tickers=%s user=%s triggered_by=%s", tickers, username, triggered_by)
    sys_settings = await get_system_settings(db)
    config = _build_config(settings, user=user, sys_settings=sys_settings)
    concurrency = settings.analyst_concurrency_limit or 1
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(ticker: str):
        async with semaphore:
            _logger.info("Portfolio analysis: running %s for user=%s", ticker, username)
            async with AsyncSessionLocal() as t_db:
                _, row = await run_analysis(ticker, trade_date, asset_type, settings, t_db, triggered_by, user=user)
                data = {
                    "id": row.id,
                    "trader_plan": row.trader_plan,
                    "portfolio_decision": row.final_decision,
                }
                await t_db.commit()
            return ticker, data

    results = await asyncio.gather(*[_run_one(t.upper()) for t in tickers], return_exceptions=True)
    ticker_reports: dict = {}
    analysis_ids: list[int] = []
    for res in results:
        if isinstance(res, Exception):
            _logger.warning("Portfolio ticker run failed for user=%s: %s", username, res)
            continue
        ticker, data = res
        analysis_ids.append(data["id"])
        ticker_reports[ticker] = {
            "trader_plan": data["trader_plan"],
            "portfolio_decision": data["portfolio_decision"],
        }
    super_report = ""
    if ticker_reports:
        try:
            user_id = user.id if user else None
            agent_access_map = {}
            if user_id is not None:
                agent_access_map = await get_user_agent_access(db, user_id)
            
            from backend.trading_agents.agent_catalog import list_analysts
            all_analyst_keys = [a.key for a in list_analysts()]
            permitted_analysts = [
                a for a in all_analyst_keys
                if agent_access_map.get(a, True)
            ]
            runtime_tool_context = await build_global_runtime_context(db, user_id)
            config["runtime_tool_context"] = runtime_tool_context
            _inject_tool_credentials(config)

            ta = TradingAgentsGraph(
                selected_analysts=permitted_analysts,
                debug=False,
                config=config,
            )
            spm_node = create_super_portfolio_manager(ta.thinking_llm)
            state_out = await asyncio.to_thread(spm_node, {"ticker_reports": ticker_reports})
            super_report = state_out.get("super_portfolio_report", "")
        except Exception as e:
            _logger.error("SuperPortfolioManager failed for user=%s: %s", username, e, exc_info=True)
            super_report = f"Portfolio synthesis failed: {e}"
    multi_row = MultiTickerAnalysis(
        trade_date=trade_date,
        asset_type=asset_type,
        super_portfolio_report=super_report,
        triggered_by=triggered_by,
        user_id=user.id if user is not None else None,
    )
    multi_row.tickers = tickers
    multi_row.analysis_ids = analysis_ids
    db.add(multi_row)
    await db.flush()
    _logger.info("Portfolio analysis complete for user=%s tickers=%s", username, tickers)
    return multi_row


async def run_analysis_task(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    task_id: str,
    user=None,
) -> None:
    """Background entrypoint for a single manual analysis run.

    Owns its own DB session, persists the result, places a paper order when the
    signal is actionable, and reports failures over the WebSocket. This is the
    orchestration that previously lived inline in the ``/analysis/run`` route.
    """
    async with AsyncSessionLocal() as db:
        try:
            _, row = await run_analysis(
                ticker, trade_date, asset_type, settings, db, "manual",
                task_id=task_id, user=user,
            )
            if row.user_id is None and user is not None:
                row.user_id = user.id
            await db.commit()
            try:
                await place_signal_order(db, ticker=ticker, row=row, settings=settings, user=user)
                await db.commit()
            except Exception as exc:
                _logger.warning("Order execution skipped for %s: %s", ticker, exc)
                await db.rollback()
        except Exception as exc:
            _logger.error("Background analysis failed: %s", exc, exc_info=True)
            try:
                await ws_manager.send(task_id, {"type": "error", "message": f"Analysis error: {exc}"})
                await ws_manager.close_task(task_id)
            except Exception:
                pass
            await db.rollback()


async def run_portfolio_task(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    user=None,
) -> None:
    """Background entrypoint for a multi-ticker portfolio analysis run."""
    async with AsyncSessionLocal() as db:
        try:
            await run_portfolio_analysis(
                tickers, trade_date, asset_type, settings, db, "manual", user=user,
            )
            await db.commit()
        except Exception as exc:
            _logger.error("Portfolio analysis failed: %s", exc, exc_info=True)
            await db.rollback()
