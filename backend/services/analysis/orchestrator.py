from __future__ import annotations
import asyncio
import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.catalog import node_progress
from backend.repositories.analysis import get_system_settings
from backend.services.stats_handler import StatsCallbackHandler
from backend.services.performance_service import get_analyst_attribution_stats
from backend.services.tool_settings_service import build_global_runtime_context
from backend.services.agent_settings_service import build_agent_runtime_context
from backend.services.tool_access_service import get_user_agent_access
from backend.services.notification_service import notify_analysis_complete
from backend.services.annotation_service import extract_chart_annotations
from backend.services.trading_orchestrator import place_signal_order

from backend.trading_agents.graph.trading_graph import TradingAgentsGraph
from backend.trading_agents.agents.schemas import PropagateResult

from .persistence import create_skeleton_result, update_result_fields, finalize_result, mark_as_failed, mark_as_cancelled
from .emitter import AnalysisEmitter
from .config_builder import build_analysis_config, inject_tool_credentials, get_historical_analyses_context, history_json_from

_logger = logging.getLogger(__name__)

REPORT_FIELDS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "macro_report", "options_report", "quant_report", "earnings_report",
    "review_report", "investment_plan", "trader_investment_plan", "final_trade_decision",
)

async def run_individual_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings,
    db: AsyncSession,
    emitter: AnalysisEmitter,
    triggered_by: str = "manual",
    user=None,
):
    """Orchestrates a single analysis run with incremental persistence and real-time updates."""
    start_time = time.time()
    username = user.username if user else "system"
    user_id = user.id if user else None
    
    # 1. Create persistent record
    row = await create_skeleton_result(db, emitter.task_id, ticker, trade_date, asset_type, triggered_by, user_id)
    await emitter.emit_status("Initializing")

    try:
        # 2. Build Configuration
        sys_settings = await get_system_settings(db)
        await emitter.emit_status("Preparing engine...")
        config = build_analysis_config(settings, user=user, sys_settings=sys_settings)
        
        # 3. Context & Intelligence gathering
        from backend.services.performance_service import get_analyst_performance_context
        attribution_md = await get_analyst_performance_context(db)
        hist_ctx = ""
        if getattr(settings, "include_historical_analyses", False):
            limit = getattr(settings, "historical_analyses_limit", 5) or 5
            hist_ctx = await get_historical_analyses_context(ticker, trade_date, db, limit=limit, output_language=settings.output_language)
        config["historical_context"] = attribution_md + hist_ctx

        # 4. Agent & Tool Access
        agent_access_map = await get_user_agent_access(db, user_id) if user_id else {}
        from backend.trading_agents.agent_catalog import list_analysts
        permitted_analysts = [a.key for a in list_analysts() if agent_access_map.get(a, True)]
        
        config["runtime_tool_context"] = await build_global_runtime_context(db, user_id)
        config["runtime_agent_context"] = await build_agent_runtime_context(db, user_id)
        inject_tool_credentials(config)

        # 5. Initialize & Run Graph
        stats_handler = StatsCallbackHandler()
        ta = TradingAgentsGraph(selected_analysts=permitted_analysts, config=config, callbacks=[stats_handler])

        prev_state = {}
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
                            await emitter.emit(prog)
                            last_node = node_name
                return
            
            # Handle debate bubbles
            for d_type, key in [("investment", "investment_debate_state"), ("risk", "risk_debate_state")]:
                d_state = chunk.get(key) or {}
                if d_state:
                    curr_count = d_state.get("count", 0)
                    is_new = False
                    if d_type == "investment" and curr_count > prev_inv_count:
                        prev_inv_count = curr_count
                        is_new = True
                    elif d_type == "risk" and curr_count > prev_risk_count:
                        prev_risk_count = curr_count
                        is_new = True
                    
                    if is_new:
                        history = d_state.get("history", "")
                        lines = [l.strip() for l in history.split("\n") if l.strip()]
                        if lines:
                            await emitter.emit_debate_bubble(d_type, lines[-1])

            # Handle incremental reports
            for key, value in chunk.items():
                if key in REPORT_FIELDS and value and value != prev_state.get(key):
                    await update_result_fields(db, row.id, **{key: value})
                    await emitter.emit_report(key, value)
                    prev_state[key] = value

        # EXECUTION
        final_state, signal = await ta.async_propagate(ticker, trade_date, asset_type, stream_observer=_stream_observer)
        
        # 6. Finalization
        duration = time.time() - start_time
        stats = stats_handler.get_stats()
        result = PropagateResult.from_state(final_state, signal)
        inv_debate = final_state.get("investment_debate_state", {}) or {}
        risk_debate = final_state.get("risk_debate_state", {}) or {}

        final_payload = {
            "signal": result.signal,
            "market_report": result.market_report,
            "sentiment_report": result.sentiment_report,
            "news_report": result.news_report,
            "fundamentals_report": result.fundamentals_report,
            "macro_report": result.macro_report,
            "options_report": result.options_report,
            "quant_report": result.quant_report,
            "earnings_report": result.earnings_report,
            "review_report": result.review_report,
            "investment_plan": result.investment_plan,
            "trader_plan": result.trader_plan,
            "final_decision": result.final_decision,
            "bull_history": history_json_from(inv_debate.get("bull_history", "")),
            "bear_history": history_json_from(inv_debate.get("bear_history", "")),
            "investment_debate_history": history_json_from(inv_debate.get("history", "")),
            "risk_debate_history": history_json_from(risk_debate.get("history", "")),
            "judge_decision": str(inv_debate.get("judge_decision", "") or ""),
            "chart_annotations": final_state.get("chart_annotations"),
            "llm_calls": stats.get("llm_calls", 0),
            "tool_calls": stats.get("tool_calls", 0),
            "tokens_in": stats.get("tokens_in", 0),
            "tokens_out": stats.get("tokens_out", 0),
            "duration_seconds": duration,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "preset_name": settings.active_preset_name or f"{settings.llm_provider}:{settings.llm_model}",
        }
        await finalize_result(db, row.id, **final_payload)
        
        # 7. Post-run tasks (background)
        from .tasks import track_background_task, extract_and_save_annotations, send_analysis_webhook, await_analysis_background_tasks
        track_background_task(extract_and_save_annotations(
            row.id, result.market_report, result.final_decision, ta.thinking_llm,
            getattr(ta, "custom_indicators", []), getattr(ta, "visual_annotations", []),
            output_language=settings.output_language
        ), task_id=emitter.task_id)
        
        track_background_task(send_analysis_webhook(
            ticker, trade_date, signal, result.final_decision, settings
        ), task_id=emitter.task_id)
        
        await await_analysis_background_tasks(emitter.task_id)
        await emitter.emit_decision(signal, result.final_decision)
        await emitter.emit_complete(row.id, signal, duration, stats.get("llm_calls", 0))
        
        _logger.info("Analysis complete task=%s ticker=%s signal=%s user=%s duration=%.2fs", emitter.task_id, ticker, signal, username, duration)
        return emitter.task_id, row

    except asyncio.CancelledError:
        _logger.info("Analysis cancelled task=%s user=%s", emitter.task_id, username)
        await mark_as_cancelled(db, row.id)
        await emitter.emit_error("Analysis cancelled.")
        raise
    except Exception as exc:
        _logger.error("Analysis failed task=%s user=%s: %s", emitter.task_id, username, exc, exc_info=True)
        await mark_as_failed(db, row.id)
        await emitter.emit_error(str(exc))
        raise
