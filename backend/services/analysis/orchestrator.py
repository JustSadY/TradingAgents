from __future__ import annotations

import asyncio
import logging
import time

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.catalog import node_progress
from backend.core.metrics import ANALYSIS_DURATION, ANALYSIS_RUNS
from backend.repositories.system_settings import get_system_settings
from backend.services.stats_handler import StatsCallbackHandler
from backend.services.token_analytics_service import estimate_cost
from backend.trading_agents.agents.runtime.debate_history import debate_messages
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

_OWNER_UNSET = object()


async def _emit_system_status(emitter: AnalysisEmitter, message: str, status: str = "starting") -> None:
    """Emit a lifecycle message without treating the message as an agent name."""
    await emitter.emit_status(agent="system", status=status, message=message)


async def _persist_terminal_status(db: AsyncSession, row_id: int, *, status: str) -> None:
    """Reset an interrupted transaction before writing a terminal state.

    A cancellation can interrupt an asyncpg commit after SQLAlchemy has expired
    ORM attributes but before the transaction is usable again.  This helper
    intentionally accepts the already-captured scalar primary key so terminal
    cleanup never dereferences an expired ``AnalysisResult`` instance.

    Terminal persistence is best effort: its own failure must not turn an
    external cancellation into a misleading "analysis failed" error.
    """
    try:
        await db.rollback()
        if status == "cancelled":
            await mark_as_cancelled(db, row_id)
        else:
            await mark_as_failed(db, row_id)
    except asyncio.CancelledError:
        # A second cancellation is still cancellation, never an analysis
        # failure.  Let the caller preserve that terminal signal.
        raise
    except Exception:
        _logger.exception("Could not persist terminal analysis status=%s row_id=%s", status, row_id)


async def _heartbeat_monitor(
    emitter: AnalysisEmitter,
    last_event_at,
    stall_timeout: float,
    *,
    sleep=asyncio.sleep,
    now=time.time,
) -> None:
    """Keep clients informed while an analysis is running, including during a stall.

    A single stall warning is emitted per silent period.  The monitor then
    continues to send ``stalled`` heartbeats until the graph produces a new
    event, rather than exiting and leaving the client with no liveness signal.
    """
    heartbeat_interval = min(30, max(10, stall_timeout / 4))
    stall_warning_sent = False
    while True:
        await sleep(heartbeat_interval)
        elapsed = now() - last_event_at()
        if elapsed > stall_timeout:
            if not stall_warning_sent:
                await emitter.emit(
                    {
                        "type": "stall_warning",
                        "seconds_since_last_event": round(elapsed, 1),
                        "threshold": stall_timeout,
                    }
                )
                _logger.warning(
                    "Stall detected task=%s — no event for %.0fs (threshold %ds)",
                    emitter.task_id,
                    elapsed,
                    stall_timeout,
                )
                stall_warning_sent = True
            await emitter.emit_progress("heartbeat", "stalled", "system")
            continue

        stall_warning_sent = False
        await emitter.emit_progress("heartbeat", "running", "system")


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
    "ratings_report",
    "short_interest_report",
    "valuation_report",
    "catalyst_report",
    "review_report",
    "synthesis_report",
    "audit_report",
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
    checkpoint_namespace: str | None = None,
    result_owner_user_id: int | None | object = _OWNER_UNSET,
):
    """Orchestrates a single analysis run with incremental persistence and real-time updates."""

    start_time = time.time()

    username = user.username if user else "system"

    user_id = user.id if user else None
    # A privileged user may time-travel another user's analysis.  Persist the
    # result under its original owner in that case; the caller's identity is
    # still used for authorization and runtime configuration below.
    persisted_user_id = user_id if result_owner_user_id is _OWNER_UNSET else result_owner_user_id

    row = await create_skeleton_result(
        db,
        emitter.task_id,
        ticker,
        trade_date,
        asset_type,
        triggered_by,
        persisted_user_id,
    )
    # Capture the scalar identifier while the initial transaction is healthy.
    # A later cancelled commit can expire ``row`` and make ``row.id`` trigger
    # a PendingRollbackError during cancellation cleanup.
    row_id = row.id

    try:
        await _emit_system_status(emitter, "Initializing")

        sys_settings = await get_system_settings(db)

        await _emit_system_status(emitter, "Preparing engine...")

        config = build_analysis_config(settings, user=user, sys_settings=sys_settings)

        # LangGraph checkpoints contain full report/tool state.  Bind every
        # normal run to its persisted AnalysisResult row; a time-travel resume
        # supplies the original row's namespace explicitly so it can only
        # resume that analysis, never another user's same ticker/date run.
        from backend.trading_agents.graph.checkpointer import checkpoint_scope

        config["checkpoint_scope"] = checkpoint_namespace or checkpoint_scope(row.user_id, row.id)

        persona_key = config.get("investor_persona")

        if persona_key and user_id:
            from backend.trading_agents.personas import get_persona as _get_builtin_persona

            if not _get_builtin_persona(persona_key):
                from sqlalchemy import select as _sel

                from backend.models.persona import UserPersona as _UP

                _custom = (
                    await db.execute(_sel(_UP).where(_UP.user_id == user_id, _UP.key == persona_key))
                ).scalar_one_or_none()

                if _custom and _custom.instructions:
                    config["investor_persona_instructions"] = _custom.instructions

        from backend.services.analysis.market_pulse_service import get_market_pulse
        from backend.services.analysis.scenario_service import get_active_scenarios
        from backend.services.performance_service import get_analyst_performance_context
        from backend.services.signal_backtest_service import get_signal_replay_context

        attribution_md = await get_analyst_performance_context(db, user_id=user_id)

        market_pulse_md = await get_market_pulse()

        scenarios_md = get_active_scenarios()

        signal_replay_md = await get_signal_replay_context(db, ticker, user_id)

        config["historical_context"] = attribution_md + market_pulse_md + scenarios_md + signal_replay_md

        permitted_analysts = await prepare_graph_config(db, user_id, config)

        if getattr(settings, "analyst_prefilter_enabled", False):
            from backend.services.analyst_prefilter_service import filter_analysts_by_history

            permitted_analysts, dropped = await filter_analysts_by_history(
                db,
                ticker,
                user_id,
                permitted_analysts,
                min_samples=int(getattr(settings, "analyst_prefilter_min_samples", 5) or 5),
                max_win_rate=float(getattr(settings, "analyst_prefilter_max_win_rate", 40.0) or 40.0),
            )

            if dropped:
                await _emit_system_status(
                    emitter,
                    f"Pre-screened out underperforming analysts: {', '.join(dropped)}",
                    status="running",
                )

        from backend.trading_agents.agents.runtime.resilience import get_report_card, init_report_card

        from .activity import AnalysisActivityTracker
        from .streaming_handler import TokenStreamingCallbackHandler

        init_report_card()
        stats_handler = StatsCallbackHandler()
        # A graph-state update is not the only sign of life: a model may be
        # generating or a tool may be fetching data for a long time before the
        # graph yields its next chunk.  Keep one tracker per task, never a
        # module-global timestamp shared by concurrent users.
        activity_tracker = AnalysisActivityTracker()

        streaming_handler = TokenStreamingCallbackHandler(emitter, activity_tracker=activity_tracker)

        ta = TradingAgentsGraph(
            selected_analysts=permitted_analysts,
            config=config,
            callbacks=[stats_handler, streaming_handler],
        )

        from backend.trading_agents.agents.data.chart_tools import active_run_context

        active_run_context.set(
            {
                "graph": ta,
                "emitter": emitter,
                "custom_indicators": [],
                "visual_annotations": [],
                "support_levels": [],
                "resistance_levels": [],
                "activity_tracker": activity_tracker,
            }
        )

        prev_state = {}

        prev_inv_count = 0

        prev_risk_count = 0

        last_node = None

        async def _stream_observer(mode: str, chunk: dict) -> None:

            nonlocal prev_inv_count, prev_risk_count, last_node
            activity_tracker.touch()

            if mode == "updates":
                for node_name in chunk or {}:
                    if node_name != last_node:
                        prog = node_progress(node_name)

                        if prog:
                            await emitter.emit(prog)

                            last_node = node_name

                return

            for d_type, key in [("investment", "investment_debate_state"), ("risk", "risk_debate_state")]:
                d_state = chunk.get(key) or {}

                if d_state:
                    curr_count = d_state.get("count", 0)

                    is_new = False
                    prior_count = prev_inv_count if d_type == "investment" else prev_risk_count

                    if d_type == "investment" and curr_count > prior_count:
                        prev_inv_count = curr_count

                        is_new = True

                    elif d_type == "risk" and curr_count > prior_count:
                        prev_risk_count = curr_count

                        is_new = True

                    if is_new:
                        history = d_state.get("history", "")
                        messages = debate_messages(history)

                        # A merged Risk Debate node can add all three
                        # perspectives in one state update. Emit every newly
                        # added *message*, not just the last physical line of
                        # a multiline response, so live and persisted views
                        # have the same transcript.
                        newly_added = max(1, curr_count - prior_count)
                        for message in messages[-newly_added:]:
                            await emitter.emit_debate_bubble(
                                d_type,
                                f"{message['sender']}: {message['content']}",
                                sender=message["sender"],
                                content=message["content"],
                            )

                        if d_type == "investment":
                            await update_result_fields(
                                db,
                                row.id,
                                investment_debate_history=messages or None,
                                bull_history=history_json_from(d_state.get("bull_history", "")),
                                bear_history=history_json_from(d_state.get("bear_history", "")),
                                judge_decision=str(d_state.get("judge_decision", "") or ""),
                            )

                        else:
                            await update_result_fields(
                                db,
                                row.id,
                                risk_debate_history=messages or None,
                            )

            for key, value in chunk.items():
                if key in REPORT_FIELDS and value and value != prev_state.get(key):
                    await update_result_fields(db, row.id, **{key: value})

                    await emitter.emit_report(key, value)

                    prev_state[key] = value

        heartbeat_task = asyncio.create_task(
            _heartbeat_monitor(
                emitter,
                activity_tracker.last_activity_at,
                float(config.get("stall_timeout_seconds", 120) or 120),
                now=time.monotonic,
            )
        )
        try:
            final_state, signal = await ta.async_propagate(
                ticker, trade_date, asset_type, stream_observer=_stream_observer
            )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        duration = time.time() - start_time

        stats = stats_handler.get_stats()

        risk_metrics = {}

        try:
            from datetime import datetime, timedelta

            from backend.core.utils import resolve_benchmark
            from backend.services.analysis.risk_metrics_service import get_risk_metrics
            from backend.services.market_data_service import get_historical_data

            benchmark_ticker = resolve_benchmark(ticker, config)

            risk_start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")

            hist_df = await get_historical_data(ticker, risk_start, trade_date)

            bench_df = await get_historical_data(benchmark_ticker, risk_start, trade_date)

            if not hist_df.empty:
                benchmark_prices = bench_df["Close"] if not bench_df.empty else None

                risk_metrics = get_risk_metrics(hist_df["Close"], benchmark_prices=benchmark_prices)

        except Exception as risk_exc:
            _logger.warning("Could not calculate risk metrics for %s: %s", ticker, risk_exc)

        result = PropagateResult.from_state(final_state, signal)

        try:
            from .run_quality import assess_run_quality

            quality = assess_run_quality(final_state, permitted_analysts, result.final_decision)
        except Exception as quality_exc:  # noqa: BLE001 — never fail a run over a quality score
            _logger.warning("Run-quality assessment failed for %s: %s", ticker, quality_exc)
            quality = None

        inv_debate = final_state.get("investment_debate_state", {}) or {}

        risk_debate = final_state.get("risk_debate_state", {}) or {}

        structured_data = final_state.get("chart_annotations") or {}

        if not isinstance(structured_data, dict):
            structured_data = {}

        trader_obj = final_state.get("trader_investment_plan_obj")

        if isinstance(trader_obj, BaseModel):
            structured_data["trader_proposal"] = trader_obj.model_dump()
        elif isinstance(trader_obj, dict):
            structured_data["trader_proposal"] = trader_obj

        _VALID_SIGNALS = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}
        raw_signal = result.signal
        if isinstance(raw_signal, str):
            raw_signal = raw_signal.strip().rstrip(".")
        if raw_signal not in _VALID_SIGNALS:
            _logger.error(
                "Signal validation FAILED: unexpected signal=%r for ticker=%s — defaulting to Hold. "
                "This indicates a prompt or parsing issue in the Portfolio Manager.",
                raw_signal,
                result.ticker,
            )
            raw_signal = "Hold"
        final_payload = {
            "signal": raw_signal,
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
            "ratings_report": result.ratings_report,
            "short_interest_report": result.short_interest_report,
            "valuation_report": result.valuation_report,
            "catalyst_report": result.catalyst_report,
            "review_report": result.review_report,
            "synthesis_report": result.synthesis_report,
            "audit_report": result.audit_report,
            "agent_qa_report": final_state.get("agent_qa_report", ""),
            "investment_plan": result.investment_plan,
            "trader_plan": result.trader_plan,
            "final_decision": result.final_decision,
            "bull_history": history_json_from(inv_debate.get("bull_history", "")),
            "bear_history": history_json_from(inv_debate.get("bear_history", "")),
            "investment_debate_history": debate_messages(inv_debate.get("history", "")) or None,
            "risk_debate_history": debate_messages(risk_debate.get("history", "")) or None,
            "judge_decision": str(inv_debate.get("judge_decision", "") or ""),
            "trader_proposal_json": final_state.get("trader_proposal_json", "{}"),
            "chart_annotations": structured_data,
            "risk_metrics": risk_metrics,
            "quality": quality,
            "degraded": any(v.get("fallback") for v in (get_report_card() or {}).values()),
            "failed_agents": [k for k, v in (get_report_card() or {}).items() if v.get("fallback")] or None,
            "llm_calls": stats.get("llm_calls", 0),
            "tool_calls": stats.get("tool_calls", 0),
            "tokens_in": stats.get("tokens_in", 0),
            "tokens_out": stats.get("tokens_out", 0),
            "duration_seconds": duration,
            "llm_provider": ta.llm_provider,
            "llm_model": ta.llm_model,
            "preset_name": (
                settings.active_preset_name
                if (
                    settings.active_preset_name
                    and settings.active_preset_name.lower() not in ("unknown", "unknown:unknown", "unknown/unknown")
                )
                else f"{(ta.llm_provider or 'Custom').strip() if ta.llm_provider and ta.llm_provider.lower() not in ('unknown', 'none') else 'Custom'}:{(ta.llm_model or 'Model').strip() if ta.llm_model and ta.llm_model.lower() not in ('unknown', 'none') else 'Model'}"
            ),
        }

        await finalize_result(db, row.id, **final_payload)

        await emitter.emit({"type": "risk_metrics", "metrics": risk_metrics})

        from .tasks import (
            await_analysis_background_tasks,
            extract_and_save_annotations,
            send_analysis_webhook,
            send_signal_flip_webhook,
            track_background_task,
        )

        try:
            from backend.repositories.analysis import get_previous_signal

            prev_signal = await get_previous_signal(db, user_id=user_id, ticker=ticker, exclude_id=row.id)
        except Exception as prev_signal_exc:  # noqa: BLE001 — never fail a run over signal-flip lookup
            _logger.debug("Previous-signal lookup failed for %s: %s", ticker, prev_signal_exc)
            prev_signal = None

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

        track_background_task(send_signal_flip_webhook(ticker, prev_signal, signal, settings), task_id=emitter.task_id)

        await await_analysis_background_tasks(emitter.task_id)

        await emitter.emit_decision(signal, result.final_decision)

        cost = estimate_cost(
            ta.llm_provider,
            ta.llm_model,
            int(stats.get("tokens_in", 0)),
            int(stats.get("tokens_out", 0)),
        )
        await emitter.emit_complete(row.id, signal, duration, stats.get("llm_calls", 0), estimated_cost_usd=cost)

        ANALYSIS_RUNS.labels(status="completed").inc()

        ANALYSIS_DURATION.observe(duration)

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

        ANALYSIS_RUNS.labels(status="cancelled").inc()

        await _persist_terminal_status(db, row_id, status="cancelled")

        try:
            await emitter.emit_error("Analysis cancelled.")
        except Exception:
            # Losing a transport during Stop should not relabel the task as a
            # background failure after it has already been cancelled.
            _logger.warning("Could not emit cancellation event task=%s", emitter.task_id, exc_info=True)

        raise

    except Exception as exc:
        _logger.exception("Analysis failed task=%s user=%s", emitter.task_id, username)

        ANALYSIS_RUNS.labels(status="failed").inc()

        await _persist_terminal_status(db, row_id, status="failed")

        exc_str = str(exc)

        err_msg = exc_str

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
