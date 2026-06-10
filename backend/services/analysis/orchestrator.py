from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.catalog import node_progress
from backend.repositories.analysis import get_system_settings
from backend.services.stats_handler import StatsCallbackHandler
from backend.trading_agents.agents.schemas import PropagateResult
from backend.trading_agents.graph.trading_graph import TradingAgentsGraph

from .config_builder import (
    build_analysis_config,
    history_json_from,
    prepare_graph_config,
)
from .emitter import AnalysisEmitter
from .persistence import (
    create_skeleton_result,
    finalize_result,
    mark_as_cancelled,
    mark_as_failed,
    update_result_fields,
)

_logger = logging.getLogger(__name__)

REPORT_FIELDS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "macro_report",
    "options_report",
    "quant_report",
    "earnings_report",
    "insider_report",
    "ownership_report",
    "catalyst_report",
    "review_report",
    "agent_qa_report",
    "investment_plan",
    "trader_investment_plan",
    "trader_proposal_json",
    "final_trade_decision",
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
        from backend.services.analysis.market_pulse_service import get_market_pulse
        from backend.services.analysis.scenario_service import get_active_scenarios
        from backend.services.performance_service import get_analyst_performance_context
        from backend.services.signal_backtest_service import get_signal_replay_context

        attribution_md = await get_analyst_performance_context(db)
        market_pulse_md = await get_market_pulse()
        scenarios_md = get_active_scenarios()
        signal_replay_md = await get_signal_replay_context(db, ticker, user_id)

        # Historical/episodic memory is now recalled semantically inside the
        # decision nodes (research manager + portfolio manager) from the vector
        # store; this start-time context carries attribution / pulse / scenario
        # summaries plus the replay of past signals on this exact ticker.
        config["historical_context"] = attribution_md + market_pulse_md + scenarios_md + signal_replay_md

        # 4. Agent & Tool Access (+ runtime context / credentials)
        permitted_analysts = await prepare_graph_config(db, user_id, config)

        # 5. Initialize & Run Graph
        from .streaming_handler import TokenStreamingCallbackHandler

        stats_handler = StatsCallbackHandler()
        streaming_handler = TokenStreamingCallbackHandler(emitter)
        ta = TradingAgentsGraph(
            selected_analysts=permitted_analysts,
            config=config,
            callbacks=[stats_handler, streaming_handler],
        )

        # Inject emitter into active_run_context for mental model updates
        from backend.trading_agents.agents.data.chart_tools import active_run_context
        active_run_context.set({
            "graph": ta,
            "emitter": emitter,
            "custom_indicators": [],
            "visual_annotations": [],
            "support_levels": [],
            "resistance_levels": [],
        })

        prev_state = {}
        prev_inv_count = 0
        prev_risk_count = 0
        last_node = None

        async def _stream_observer(mode: str, chunk: dict) -> None:
            nonlocal prev_inv_count, prev_risk_count, last_node
            if mode == "updates":
                for node_name in chunk or {}:
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

        # Risk Metrics Calculation
        risk_metrics = {}
        try:
            from datetime import datetime, timedelta

            from backend.core.utils import resolve_benchmark
            from backend.services.analysis.risk_metrics_service import get_risk_metrics
            from backend.services.market_data_service import get_historical_data

            # Resolve benchmark
            benchmark_ticker = resolve_benchmark(ticker, config)

            # Fetch 1 year of data for risk metrics
            risk_start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
            hist_df = await get_historical_data(ticker, risk_start, trade_date)
            bench_df = await get_historical_data(benchmark_ticker, risk_start, trade_date)

            if not hist_df.empty:
                benchmark_prices = bench_df["Close"] if not bench_df.empty else None
                risk_metrics = get_risk_metrics(hist_df["Close"], benchmark_prices=benchmark_prices)
        except Exception as risk_exc:
            _logger.warning("Could not calculate risk metrics for %s: %s", ticker, risk_exc)

        result = PropagateResult.from_state(final_state, signal)
        inv_debate = final_state.get("investment_debate_state", {}) or {}
        risk_debate = final_state.get("risk_debate_state", {}) or {}

        # Capture structured results for non-regex extraction
        structured_data = final_state.get("chart_annotations") or {}
        if not isinstance(structured_data, dict):
            structured_data = {}

        # Add LLM generated plan details if available in state.
        # Note: The graph currently stores the rendered text in trader_investment_plan.
        # We check for a raw object if the agent supports structured output.
        trader_obj = final_state.get("trader_investment_plan_obj")
        if trader_obj:
            if hasattr(trader_obj, "dict"):
                structured_data["trader_proposal"] = trader_obj.dict()
            elif isinstance(trader_obj, dict):
                structured_data["trader_proposal"] = trader_obj

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
            "insider_report": result.insider_report,
            "ownership_report": result.ownership_report,
            "catalyst_report": result.catalyst_report,
            "review_report": result.review_report,
            "agent_qa_report": final_state.get("agent_qa_report", ""),
            "investment_plan": result.investment_plan,
            "trader_plan": result.trader_plan,
            "final_decision": result.final_decision,
            "bull_history": history_json_from(inv_debate.get("bull_history", "")),
            "bear_history": history_json_from(inv_debate.get("bear_history", "")),
            "investment_debate_history": history_json_from(inv_debate.get("history", "")),
            "risk_debate_history": history_json_from(risk_debate.get("history", "")),
            "judge_decision": str(inv_debate.get("judge_decision", "") or ""),
            "trader_proposal_json": final_state.get("trader_proposal_json", "{}"),
            "chart_annotations": structured_data,
            "risk_metrics": risk_metrics,
            "llm_calls": stats.get("llm_calls", 0),
            "tool_calls": stats.get("tool_calls", 0),
            "tokens_in": stats.get("tokens_in", 0),
            "tokens_out": stats.get("tokens_out", 0),
            "duration_seconds": duration,
            "llm_provider": ta.llm_provider,
            "llm_model": ta.llm_model,
            "preset_name": (
                settings.active_preset_name
                if (settings.active_preset_name and settings.active_preset_name.lower() not in ("unknown", "unknown:unknown", "unknown/unknown"))
                else f"{(ta.llm_provider or 'Custom').strip() if ta.llm_provider and ta.llm_provider.lower() not in ('unknown', 'none') else 'Custom'}:{(ta.llm_model or 'Model').strip() if ta.llm_model and ta.llm_model.lower() not in ('unknown', 'none') else 'Model'}"
            ),
        }
        await finalize_result(db, row.id, **final_payload)
        await emitter.emit({"type": "risk_metrics", "metrics": risk_metrics})

        # 7. Post-run tasks (background)
        from .tasks import (
            await_analysis_background_tasks,
            extract_and_save_annotations,
            send_analysis_webhook,
            track_background_task,
        )

        track_background_task(
            extract_and_save_annotations(
                row.id,
                result.market_report,
                result.final_decision,
                ta.thinking_llm,
                getattr(ta, "custom_indicators", []),
                getattr(ta, "visual_annotations", []),
                getattr(ta, "support_levels", []),
                getattr(ta, "resistance_levels", []),
                output_language=settings.output_language,
            ),
            task_id=emitter.task_id,
        )

        track_background_task(
            send_analysis_webhook(ticker, trade_date, signal, result.final_decision, settings), task_id=emitter.task_id
        )

        await await_analysis_background_tasks(emitter.task_id)
        await emitter.emit_decision(signal, result.final_decision)
        await emitter.emit_complete(row.id, signal, duration, stats.get("llm_calls", 0))

        _logger.info(
            "Analysis complete task=%s ticker=%s signal=%s user=%s duration=%.2fs",
            emitter.task_id,
            ticker,
            signal,
            username,
            duration,
        )
        return emitter.task_id, row

    except asyncio.CancelledError:
        _logger.info("Analysis cancelled task=%s user=%s", emitter.task_id, username)
        await mark_as_cancelled(db, row.id)
        await emitter.emit_error("Analysis cancelled.")
        raise
    except Exception as exc:
        _logger.error("Analysis failed task=%s user=%s: %s", emitter.task_id, username, exc, exc_info=True)
        await mark_as_failed(db, row.id)

        exc_str = str(exc)
        err_msg = exc_str

        # Check for model not found / 404 or configuration errors
        if "404" in exc_str or "not_found" in exc_str.lower() or "not found" in exc_str.lower():
            err_msg = f"Model not found or invalid provider configuration (404 Error: {exc_str})"
        elif "401" in exc_str or "unauthorized" in exc_str.lower() or "invalid api key" in exc_str.lower():
            err_msg = f"Authentication failed or invalid API key (401 Error: {exc_str})"
        elif "400" in exc_str or "bad_request" in exc_str.lower() or "bad request" in exc_str.lower():
            err_msg = f"Invalid request parameters or model settings (400 Error: {exc_str})"
        elif "429" in exc_str or "rate_limit" in exc_str.lower() or "rate limit" in exc_str.lower():
            err_msg = f"Rate limit exceeded (429 Error: {exc_str})"

        await emitter.emit_error(err_msg)
        raise
