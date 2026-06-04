import asyncio
import logging
import time
import uuid
import backend.bootstrap  # noqa: F401  (sets engine env before importing the engine)
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.websocket import ws_manager
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings
_logger = logging.getLogger(__name__)
_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_REPORT_FIELDS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "macro_report", "options_report", "quant_report", "earnings_report",
    "review_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
)
async def _get_historical_analyses_context(
    ticker: str, trade_date: str, db: AsyncSession, limit: int = 5
) -> str:
    from sqlalchemy import select, desc as _desc
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.ticker == ticker)
        .where(AnalysisResult.trade_date < trade_date)
        .order_by(_desc(AnalysisResult.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    if not rows:
        return ""
    parts = [f"=== {ticker} GEÇMİŞ ANALİZ RAPORLARI ===\n"]
    for row in reversed(rows):
        parts.append(f"--- Tarih: {row.trade_date} | Sinyal: {row.signal or 'N/A'} ---")
        for label, field in [
            ("Piyasa Raporu", row.market_report),
            ("Haber Raporu", row.news_report),
            ("Temel Analiz", row.fundamentals_report),
            ("Son Karar", row.final_decision),
        ]:
            if field and field.strip():
                parts.append(f"{label}:\n{field[:400].strip()}...")
        parts.append("")
    return "\n".join(parts)
def _build_config(settings: AppSettings, user=None, sys_settings=None) -> dict:
    from backend.trading_agents.graph.trading_graph import DEFAULT_CONFIG
    import tempfile, os as _os
    _tmp = tempfile.gettempdir()
    cfg: dict = {
        "data_cache_dir": _os.path.join(_tmp, "ta_cache"),
        "results_dir":    _os.path.join(_tmp, "ta_results"),
        "memory_log_path": _os.path.join(_tmp, "ta_memory.md"),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model or "gpt-4o-mini",
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_rounds,
        "output_language": settings.output_language or "English",
        "investor_persona": settings.investor_persona or "conservative",
        "analyst_concurrency_limit": settings.analyst_concurrency_limit or 1,
        "skip_disk_log": True,
        "checkpoint_enabled": getattr(settings, "checkpoint_enabled", False),
        "max_recur_limit": getattr(settings, "max_recur_limit", 1000) or 1000,
        "news_article_limit": getattr(settings, "news_article_limit", 20) or 20,
        "global_news_article_limit": getattr(settings, "global_news_article_limit", 10) or 10,
        "global_news_lookback_days": getattr(settings, "global_news_lookback_days", 7) or 7,
        "data_vendors": {
            "core_stock_apis": getattr(settings, "data_vendor_core_stock", None) or settings.active_data_vendor,
            "technical_indicators": getattr(settings, "data_vendor_technicals", None) or settings.active_data_vendor,
            "fundamental_data": getattr(settings, "data_vendor_fundamentals", None) or settings.active_data_vendor,
            "news_data": getattr(settings, "data_vendor_news", None) or settings.active_data_vendor,
        },
        "analyst_models": getattr(settings, "analyst_models", {}) or {},
        "reddit_enabled": getattr(settings, "reddit_enabled", True),
        "is_admin": getattr(user, "is_admin", False) if user is not None else False,
        "has_user": user is not None,
    }
    if getattr(settings, "backend_url", None):
        cfg["backend_url"] = settings.backend_url
    if getattr(settings, "benchmark_ticker", None):
        cfg["benchmark_ticker"] = settings.benchmark_ticker
    if getattr(settings, "azure_deployment", None):
        cfg["azure_deployment_name"] = settings.azure_deployment
    if getattr(settings, "openai_reasoning_effort", None):
        cfg["openai_reasoning_effort"] = settings.openai_reasoning_effort
    if getattr(settings, "anthropic_effort", None):
        cfg["anthropic_effort"] = settings.anthropic_effort
    if getattr(settings, "google_thinking_level", None):
        cfg["google_thinking_level"] = settings.google_thinking_level
    if sys_settings:
        if getattr(sys_settings, "searxng_url", None):
            cfg["searxng_url"] = sys_settings.searxng_url
        if getattr(sys_settings, "reddit_client_id", None):
            cfg["reddit_client_id"] = sys_settings.reddit_client_id
        if getattr(sys_settings, "reddit_client_secret", None):
            cfg["reddit_client_secret"] = sys_settings.reddit_client_secret
        if getattr(sys_settings, "reddit_user_agent", None):
            cfg["reddit_user_agent"] = sys_settings.reddit_user_agent
        if getattr(sys_settings, "alpha_vantage_api_key", None):
            cfg["alpha_vantage_api_key"] = sys_settings.alpha_vantage_api_key
    if user is not None:
        from backend.core.config import get_settings as _cfg
        from backend.services.user_service import get_user_api_key, decrypt_api_keys
        try:
            fernet = _cfg().get_fernet()
            user_key = get_user_api_key(user, settings.llm_provider, fernet)
            if user.api_keys_enc:
                cfg["user_api_keys"] = decrypt_api_keys(user.api_keys_enc, fernet)
            else:
                cfg["user_api_keys"] = {}
        except Exception:
            user_key = None
            cfg["user_api_keys"] = {}
        if user_key:
            cfg["api_key"] = user_key
        elif not getattr(user, "is_admin", False):
            raise ValueError(
                f"No API key set for provider '{settings.llm_provider}'. "
                "Go to Settings → API Keys to add your key."
            )
    return cfg
def _history_json_from(value) -> str:
    import json as _json
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return _json.dumps(value, ensure_ascii=False)
    return str(value)
def _extract_stats(handler) -> dict:
    try:
        return handler.get_stats()
    except Exception:
        return {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
async def cancel_analysis(task_id: str) -> bool:
    task = _RUNNING_TASKS.pop(task_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False
async def _send_analysis_webhook(ticker, trade_date, signal, final_decision, settings):
    try:
        from backend.services.notification_service import notify_analysis_complete
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
) -> None:
    import json as _json
    from backend.core.database import AsyncSessionLocal
    from backend.services.annotation_service import extract_chart_annotations
    from sqlalchemy import select
    try:
        annotations = await extract_chart_annotations(market_report, final_decision, quick_llm)
        if not annotations:
            annotations = {}
        if custom_indicators:
            annotations["custom_indicators"] = custom_indicators
        if visual_annotations:
            annotations["annotations"] = visual_annotations
        if not annotations:
            return
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(AnalysisResult).where(AnalysisResult.id == analysis_id))
            row = result.scalar_one_or_none()
            if row:
                row.chart_annotations = _json.dumps(annotations, ensure_ascii=False)
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
    from backend.trading_agents.graph.trading_graph import TradingAgentsGraph
    if task_id is None:
        task_id = str(uuid.uuid4())
    current = asyncio.current_task()
    if current:
        _RUNNING_TASKS[task_id] = current
    username = user.username if user else "system"
    _logger.info("Starting analysis task=%s ticker=%s date=%s user=%s", task_id, ticker, trade_date, username)
    await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "Initializing"})
    from backend.services.stats_handler import StatsCallbackHandler
    from backend.core.catalog import node_progress
    loop = asyncio.get_running_loop()
    def _emit(event: dict) -> None:
        try:
            asyncio.run_coroutine_threadsafe(ws_manager.send(task_id, event), loop)
        except Exception:
            pass
    stats_handler = StatsCallbackHandler()
    start = time.time()
    try:
        from sqlalchemy import select
        from backend.models.system_settings import SystemSettings
        sys_res = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
        sys_settings = sys_res.scalar_one_or_none()
        await ws_manager.send(task_id, {"type": "status", "status": "starting", "agent": "LLM istemcisi hazırlanıyor..."})
        config = _build_config(settings, user=user, sys_settings=sys_settings)
        from backend.services.performance_service import get_analyst_attribution_stats
        from sqlalchemy.exc import PendingRollbackError
        attribution_md = ""
        try:
            try:
                attribution_data = await get_analyst_attribution_stats(db)
            except PendingRollbackError:
                await db.rollback()
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
            db_ctx = await _get_historical_analyses_context(ticker, trade_date, db, limit=limit)
            if db_ctx:
                hist_ctx = db_ctx
        config["historical_context"] = attribution_md + hist_ctx
        ta = TradingAgentsGraph(
            selected_analysts=settings.selected_analysts,
            debug=False,
            config=config,
        )
        def _patched_invoke(state, config_arg=None, **kwargs):
            if config_arg is not None and "config" not in kwargs:
                kwargs["config"] = config_arg
            kwargs.pop("stream_mode", None)
            cfg = dict(kwargs.pop("config", None) or {})
            cfg["callbacks"] = list(cfg.get("callbacks") or []) + [stats_handler]
            prev_state: dict = {}
            final: dict = {}
            prev_inv_count = 0
            prev_risk_count = 0
            last_node = None
            for mode, chunk in ta.graph.stream(
                state, stream_mode=["updates", "values"], config=cfg, **kwargs
            ):
                if mode == "updates":
                    for node_name in (chunk or {}):
                        if node_name != last_node:
                            prog = node_progress(node_name)
                            if prog:
                                _emit(prog)
                                last_node = node_name
                else:
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
                    final = chunk
            return final
        ta.graph.invoke = _patched_invoke
        final_state, signal = await ta.async_propagate(ticker, trade_date, asset_type)
        stats = _extract_stats(stats_handler)
        duration = time.time() - start
        from backend.trading_agents.agents.schemas import PropagateResult
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
        asyncio.create_task(_extract_and_save_annotations(
            row.id, 
            result.market_report, 
            result.final_decision, 
            ta.thinking_llm,
            getattr(ta, "custom_indicators", []),
            getattr(ta, "visual_annotations", [])
        ))
        asyncio.create_task(_send_analysis_webhook(
            ticker, trade_date, signal, result.final_decision, settings
        ))
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
        await ws_manager.send(task_id, {"type": "error", "message": "Analiz iptal edildi."})
        raise
    except Exception as exc:
        _logger.error("Analysis failed task=%s user=%s: %s", task_id, username, exc, exc_info=True)
        await ws_manager.send(task_id, {"type": "error", "message": str(exc)})
        raise
    finally:
        _RUNNING_TASKS.pop(task_id, None)
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
    from backend.trading_agents.graph.trading_graph import TradingAgentsGraph
    from backend.models.portfolio_analysis import MultiTickerAnalysis
    from backend.core.database import AsyncSessionLocal
    from sqlalchemy import select
    from backend.models.system_settings import SystemSettings
    username = user.username if user else "system"
    _logger.info("Starting portfolio analysis for tickers=%s user=%s triggered_by=%s", tickers, username, triggered_by)
    sys_res = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    sys_settings = sys_res.scalar_one_or_none()
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
            ta = TradingAgentsGraph(
                selected_analysts=settings.selected_analysts,
                debug=False,
                config=config,
            )
            from backend.trading_agents.agents.managers.super_portfolio_manager import create_super_portfolio_manager
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
    from backend.core.database import AsyncSessionLocal
    from backend.services.trading_orchestrator import place_signal_order
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
                await ws_manager.send(task_id, {"type": "error", "message": f"Analiz hatası: {exc}"})
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
    from backend.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            await run_portfolio_analysis(
                tickers, trade_date, asset_type, settings, db, "manual", user=user,
            )
            await db.commit()
        except Exception as exc:
            _logger.error("Portfolio analysis failed: %s", exc, exc_info=True)
            await db.rollback()
