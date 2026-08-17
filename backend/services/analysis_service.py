"""Lightweight facade for the decomposed analysis subsystem.

Responsibilities have been moved to:
- .orchestrator: High-level task flow (run_analysis)
- .persistence: Incremental and final DB updates
- .emitter: Real-time event broadcasting (WS)
- .config_builder: Config dictionary assembly
- .tasks: Background extraction and notification tasks
- .portfolio_orchestrator: Multi-ticker synthesis

DESIGN TARGET (Out-of-Process Scaling):
Currently, task tracking is managed in-memory via `_RUNNING_TASKS` and `_TASK_REGISTRY`
under a single Uvicorn process. To support high concurrent LLM runs:
1. Keep functions inside the `analysis` sub-module (especially orchestrator and persistence) stateless
   and db-session encapsulated so they can easily be deported to arq / Celery workers.
2. Rely on DB-driven updates and avoid coupling to local process memory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.analysis_runtime import AnalysisTaskMeta, get_analysis_runtime
from backend.core.database import AsyncSessionLocal
from backend.core.rls_context import set_user_background_context
from backend.models.settings import AppSettings
from backend.services.execution.base import OrderResult
from backend.services.trading_orchestrator import auto_execute_signals_enabled, place_signal_order

from .analysis.emitter import AnalysisEmitter
from .analysis.orchestrator import run_individual_analysis
from .analysis.portfolio_orchestrator import run_portfolio_analysis
from .analysis.task_lifecycle import AnalysisTaskStatus, TerminalCoordinator, TerminalResult

_logger = logging.getLogger(__name__)
runtime = get_analysis_runtime()
# Compatibility alias for existing regression tests during the boundary migration.
task_store = runtime

_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_TASK_REGISTRY: dict[str, dict] = {}
_TASK_OWNERS: dict[str, int | None] = {}
_HEARTBEAT_TASKS: dict[str, asyncio.Task] = {}
_TERMINAL_COORDINATOR = TerminalCoordinator()
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _time_travel_checkpoint_overrides(
    *,
    strategy_context: dict,
    historical_context: str,
) -> dict:
    """Return server-owned state that makes a checkpoint replay non-learning."""
    return {
        "strategy_context": strategy_context,
        "analysis_mode": "time_travel",
        "learning_eligible": False,
        "past_context": historical_context,
    }


async def register_task_owner(task_id: str, user_id: int | None) -> None:
    _TASK_OWNERS[task_id] = user_id
    await runtime.set_owner(task_id, user_id)


async def clear_task_owner(task_id: str) -> None:
    _TASK_OWNERS.pop(task_id, None)
    await runtime.clear_owner(task_id)


async def is_task_owner(task_id: str, user_id: int | None, is_admin: bool = False) -> bool:
    """Return True if *user* may subscribe to *task_id*'s event stream."""
    if is_admin:
        return True
    owner = _TASK_OWNERS.get(task_id)
    if owner is None:
        owner = await runtime.owner(task_id)
    return owner is not None and owner == user_id


async def cancel_local_task(task_id: str) -> bool:
    """Cancel ``task_id`` if it is running in THIS process."""
    task = _RUNNING_TASKS.get(task_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def cancel_analysis(task_id: str) -> bool:
    """Cancel a run wherever it is executing."""
    await runtime.request_cancel(task_id)
    await cancel_local_task(task_id)
    await runtime.publish_cancel(task_id)
    return True


async def get_active_tasks_for_user(user_id: int | None) -> list[dict]:
    """Returns a list of active tasks for the given user (all processes)."""
    tasks = [{"task_id": tid, **meta} for tid, meta in _TASK_REGISTRY.items() if meta.get("user_id") == user_id]
    if user_id is not None:
        seen = {t["task_id"] for t in tasks}
        tasks.extend(
            {"task_id": meta.task_id, **meta.store_payload()}
            for meta in await runtime.active_tasks(user_id)
            if meta.task_id not in seen
        )
    return tasks


async def register_queued_task(
    task_id: str, *, ticker: str, trade_date: str, asset_type: str, user_id: int | None
) -> None:
    _TERMINAL_COORDINATOR.reset(task_id)
    meta = {
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type,
        "user_id": user_id,
        "started_at": time.time(),
        "status": "queued",
        "retry_count": 0,
    }
    from backend.core.config import get_settings

    if get_settings().ANALYSIS_QUEUE_MODE.strip().lower() != "worker":
        _TASK_REGISTRY[task_id] = meta
        _TASK_OWNERS[task_id] = user_id
    await runtime.register(AnalysisTaskMeta.from_store_payload(task_id, meta))


async def discard_queued_task(task_id: str, user_id: int | None) -> None:
    """Remove a task registration when dispatch fails before execution."""
    await terminalize_task(
        task_id,
        user_id,
        TerminalResult(AnalysisTaskStatus.FAILED, reason="dispatch failed before execution"),
    )


async def _heartbeat_loop(task_id: str, user_id: int | None) -> None:
    """Renew shared and database task leases until terminal cleanup."""
    try:
        while True:
            await runtime.heartbeat(task_id, user_id)
            try:
                from sqlalchemy import update

                from backend.models.analysis import AnalysisResult

                async with AsyncSessionLocal() as db:
                    if user_id is not None:
                        await set_user_background_context(db, user_id)
                    await db.execute(
                        update(AnalysisResult)
                        .where(AnalysisResult.task_id == task_id)
                        .where(AnalysisResult.status.in_(("queued", "running")))
                        .values(heartbeat_at=datetime.now(UTC), worker_id=_WORKER_ID)
                    )
                    await db.commit()
            except Exception:
                _logger.warning("Could not renew analysis DB lease task=%s", task_id, exc_info=True)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise


async def _track_running_task(
    task_id: str,
    *,
    ticker: str,
    trade_date: str,
    asset_type: str,
    user_id: int | None,
) -> None:
    """Register the current coroutine after its cancellation gate passed."""
    current = asyncio.current_task()
    if current is None:
        return
    _TERMINAL_COORDINATOR.reset(task_id)
    existing = await runtime.metadata(task_id)
    meta = {
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type,
        "user_id": user_id,
        "started_at": existing.started_at if existing is not None else time.time(),
        "status": "running",
        "retry_count": existing.retry_count if existing is not None else 0,
    }
    _RUNNING_TASKS[task_id] = current
    _TASK_REGISTRY[task_id] = meta
    _TASK_OWNERS[task_id] = user_id
    await runtime.register(AnalysisTaskMeta.from_store_payload(task_id, meta))
    old_heartbeat = _HEARTBEAT_TASKS.pop(task_id, None)
    if old_heartbeat:
        old_heartbeat.cancel()
    _HEARTBEAT_TASKS[task_id] = asyncio.create_task(_heartbeat_loop(task_id, user_id))


async def terminalize_task(task_id: str, user_id: int | None, result: TerminalResult) -> bool:
    """Idempotently remove runtime tracking after a product terminal event."""

    async def cleanup() -> None:
        _RUNNING_TASKS.pop(task_id, None)
        _TASK_REGISTRY.pop(task_id, None)
        heartbeat = _HEARTBEAT_TASKS.pop(task_id, None)
        if heartbeat:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
        _TASK_OWNERS.pop(task_id, None)
        await runtime.complete(task_id, user_id)

    won = await _TERMINAL_COORDINATOR.run_once(task_id, result, cleanup)
    if not won:
        existing = _TERMINAL_COORDINATOR.result(task_id)
        if existing is not None and existing != result:
            _logger.warning(
                "Ignoring duplicate terminal transition task=%s existing=%s requested=%s",
                task_id,
                existing.status,
                result.status,
            )
    return won


def get_terminal_result(task_id: str) -> TerminalResult | None:
    return _TERMINAL_COORDINATOR.result(task_id)


async def _emit_cancelled_task(task_id: str, *, close: bool = True) -> None:
    emitter = AnalysisEmitter(task_id)
    try:
        await emitter.emit_error("Analysis cancelled.")
    finally:
        if close:
            await emitter.close()


async def _emit_auto_order_result(
    emitter: AnalysisEmitter,
    *,
    row,
    ticker: str,
    result: OrderResult | None = None,
    outcome: str | None = None,
    message: str = "",
    reason_code: str | None = None,
) -> None:
    action = None
    try:
        from backend.core.constants import SIGNAL_TO_ACTION

        action = SIGNAL_TO_ACTION.get(getattr(row, "signal", None))
    except Exception:
        pass

    broker_status = (getattr(result, "status", "") or "").upper() if result else None
    if outcome is None:
        if broker_status in {"FILLED", "PARTIALLY_FILLED"}:
            outcome = "filled"
        elif broker_status == "SKIPPED":
            outcome = "skipped"
        elif broker_status:
            outcome = "rejected"
        else:
            outcome = "skipped"

    try:
        await emitter.emit_order_result(
            analysis_id=int(row.id),
            ticker=ticker,
            action=action,
            signal=getattr(row, "signal", None),
            outcome=outcome,
            broker_status=broker_status,
            order_id=getattr(result, "order_id", None) if result else None,
            filled_quantity=getattr(result, "filled_quantity", None) if result else None,
            filled_price=getattr(result, "filled_price", None) if result else None,
            commission=getattr(result, "commission", None) if result else None,
            message=message or getattr(result, "message", "") or "",
            reason_code=reason_code or getattr(result, "reason_code", None),
        )
    except Exception:
        _logger.exception("Could not emit auto-order outcome for analysis_id=%s", getattr(row, "id", None))


def _snapshot_auto_order_context(row) -> SimpleNamespace:
    return SimpleNamespace(
        id=getattr(row, "id", None),
        signal=getattr(row, "signal", None),
        quality=getattr(row, "quality", None),
        chart_annotations=getattr(row, "chart_annotations", None),
        portfolio_decision_json=getattr(row, "portfolio_decision_json", None),
        decision_transition_json=getattr(row, "decision_transition_json", None),
        strategy_update_status=getattr(row, "strategy_update_status", None),
        analysis_mode=getattr(row, "analysis_mode", "live"),
        learning_eligible=getattr(row, "learning_eligible", True),
        final_decision=getattr(row, "final_decision", ""),
    )


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    task_id: str | None = None,
    user=None,
    *,
    defer_terminal_cleanup: bool = False,
):
    import uuid

    if task_id is None:
        task_id = str(uuid.uuid4())

    user_id = user.id if user else None
    emitter = AnalysisEmitter(task_id)
    terminal_result = TerminalResult(AnalysisTaskStatus.FAILED, reason="analysis failed")
    try:
        if await runtime.is_cancelled(task_id):
            await emitter.emit_error("Analysis cancelled.")
            terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="cancelled before start")
            raise asyncio.CancelledError

        await _track_running_task(
            task_id,
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            user_id=user_id,
        )
        if await runtime.is_cancelled(task_id):
            await emitter.emit_error("Analysis cancelled.")
            terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="cancelled after registration")
            raise asyncio.CancelledError
        value = await run_individual_analysis(ticker, trade_date, asset_type, settings, db, emitter, triggered_by, user)
        terminal_result = TerminalResult(AnalysisTaskStatus.COMPLETED)
        return value
    except asyncio.CancelledError:
        terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="analysis coroutine cancelled")
        raise
    except Exception as exc:
        terminal_result = TerminalResult(AnalysisTaskStatus.FAILED, reason=type(exc).__name__)
        if getattr(emitter, "terminal_event_emitted", False):
            exc._analysis_terminal_event_emitted = True
        raise
    finally:
        if not defer_terminal_cleanup:
            await terminalize_task(task_id, user_id, terminal_result)
            await emitter.close()


async def run_analysis_task(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    task_id: str,
    user=None,
    triggered_by: str = "manual",
) -> None:
    if user:
        from backend.core.log_handler import current_user_id

        current_user_id.set(user.id)
    user_id = user.id if user else None
    retry_scheduled = False
    analysis_completed = False
    async with AsyncSessionLocal() as db:
        if user is not None:
            await set_user_background_context(db, user.id)
        try:
            _, row = await run_analysis(
                ticker,
                trade_date,
                asset_type,
                settings,
                db,
                triggered_by,
                task_id=task_id,
                user=user,
                defer_terminal_cleanup=True,
            )
            order_context = _snapshot_auto_order_context(row)
            try:
                await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                await db.rollback()
                _logger.exception("Could not persist completed analysis task=%s", task_id)
                await AnalysisEmitter(task_id).emit_error("Analysis could not be saved. Please try again.")
                await terminalize_task(
                    task_id,
                    user_id,
                    TerminalResult(AnalysisTaskStatus.FAILED, reason="final analysis commit failed"),
                )
                return
            analysis_completed = True
            emitter = AnalysisEmitter(task_id)

            if await runtime.is_cancelled(task_id):
                _logger.info("Skipping signal order for cancelled analysis task=%s", task_id)
                await _emit_auto_order_result(
                    emitter,
                    row=order_context,
                    ticker=ticker,
                    outcome="skipped",
                    message="Analysis was cancelled before any automatic order was sent.",
                    reason_code="cancelled",
                )
            elif not auto_execute_signals_enabled(settings):
                await _emit_auto_order_result(
                    emitter,
                    row=order_context,
                    ticker=ticker,
                    outcome="skipped",
                    message="Automatic signal execution is disabled in settings.",
                    reason_code="auto_execution_disabled",
                )
            else:
                try:
                    result = await place_signal_order(
                        db,
                        ticker=ticker,
                        row=order_context,
                        settings=settings,
                        user=user,
                        include_skip_result=True,
                    )
                    if await runtime.is_cancelled(task_id):
                        await db.rollback()
                        await _emit_auto_order_result(
                            emitter,
                            row=order_context,
                            ticker=ticker,
                            outcome="skipped",
                            message="Analysis was cancelled before the automatic order could be committed.",
                            reason_code="cancelled",
                        )
                    else:
                        await db.commit()
                        await _emit_auto_order_result(emitter, row=order_context, ticker=ticker, result=result)
                except asyncio.CancelledError:
                    await db.rollback()
                    await _emit_auto_order_result(
                        emitter,
                        row=order_context,
                        ticker=ticker,
                        outcome="skipped",
                        message="Analysis was cancelled before the automatic order could be committed.",
                        reason_code="cancelled",
                    )
                    raise
                except Exception as exc:
                    await db.rollback()
                    _logger.warning("Order execution skipped for %s: %s", ticker, exc)
                    await _emit_auto_order_result(
                        emitter,
                        row=order_context,
                        ticker=ticker,
                        outcome="error",
                        message="Automatic order execution failed; the analysis remains available.",
                        reason_code="execution_error",
                    )
            await terminalize_task(task_id, user_id, TerminalResult(AnalysisTaskStatus.COMPLETED))
        except asyncio.CancelledError:
            _logger.info("Background analysis cancelled task=%s", task_id)
            try:
                await db.commit()
            except Exception:
                await db.rollback()
                _logger.exception("Could not persist cancelled analysis task=%s", task_id)
            await terminalize_task(
                task_id,
                user_id,
                TerminalResult(AnalysisTaskStatus.CANCELLED, reason="background task cancelled"),
            )
            raise
        except Exception as exc:
            if await runtime.is_cancelled(task_id):
                _logger.info("Background analysis stopped during failure cleanup task=%s", task_id)
                await db.rollback()
                await _emit_cancelled_task(task_id, close=False)
                await terminalize_task(
                    task_id,
                    user_id,
                    TerminalResult(AnalysisTaskStatus.CANCELLED, reason="cancel marker observed during failure cleanup"),
                )
                return
            if analysis_completed or getattr(exc, "_analysis_terminal_event_emitted", False):
                _logger.info("Not retrying analysis with an emitted terminal event task=%s", task_id)
                status = AnalysisTaskStatus.COMPLETED if analysis_completed else AnalysisTaskStatus.FAILED
                await terminalize_task(task_id, user_id, TerminalResult(status, reason=type(exc).__name__))
                return
            _logger.exception("Background analysis failed")
            try:
                retry_scheduled = await _maybe_retry_analysis(ticker, trade_date, asset_type, settings, task_id, user)
            except Exception:
                _logger.exception("Analysis retry failed for task=%s", task_id)
            if not retry_scheduled:
                if await runtime.is_cancelled(task_id):
                    await _emit_cancelled_task(task_id, close=False)
                    terminal_result = TerminalResult(
                        AnalysisTaskStatus.CANCELLED,
                        reason="cancel marker observed after retry decision",
                    )
                else:
                    await AnalysisEmitter(task_id).emit_error("Analysis failed before completion. Please try again.")
                    terminal_result = TerminalResult(AnalysisTaskStatus.FAILED, reason=type(exc).__name__)
                await terminalize_task(task_id, user_id, terminal_result)
        finally:
            if not retry_scheduled:
                try:
                    await AnalysisEmitter(task_id).close()
                except Exception:
                    _logger.debug("Could not close analysis event stream task=%s", task_id, exc_info=True)


async def _maybe_retry_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    task_id: str,
    user=None,
) -> bool:
    """Return False to ensure failed tasks are not automatically re-enqueued."""
    return False


async def run_portfolio_task(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    user=None,
    task_id: str | None = None,
) -> None:
    if user:
        from backend.core.log_handler import current_user_id

        current_user_id.set(user.id)
    user_id = user.id if user else None
    terminal_result = TerminalResult(AnalysisTaskStatus.COMPLETED)
    emitter = AnalysisEmitter(task_id) if task_id else None
    try:
        if task_id:
            if await runtime.is_cancelled(task_id):
                terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="cancelled before portfolio start")
                await _emit_cancelled_task(task_id, close=False)
                return
            await _track_running_task(
                task_id,
                ticker=", ".join(tickers),
                trade_date=trade_date,
                asset_type=asset_type,
                user_id=user_id,
            )
            if await runtime.is_cancelled(task_id):
                raise asyncio.CancelledError

        async with AsyncSessionLocal() as db:
            if user is not None:
                await set_user_background_context(db, user.id)
            await run_portfolio_analysis(
                tickers,
                trade_date,
                asset_type,
                settings,
                db,
                "manual",
                user=user,
                task_id=task_id,
            )
            await db.commit()
    except asyncio.CancelledError:
        terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="portfolio task cancelled")
        _logger.info("Portfolio analysis cancelled task=%s", task_id)
        if task_id:
            await _emit_cancelled_task(task_id, close=False)
        raise
    except Exception as exc:
        terminal_result = TerminalResult(AnalysisTaskStatus.FAILED, reason=type(exc).__name__)
        _logger.exception("Portfolio analysis failed")
        if emitter:
            await emitter.emit_error("Portfolio analysis failed")
    finally:
        if task_id:
            await terminalize_task(task_id, user_id, terminal_result)
            if emitter:
                await emitter.close()


async def rollback_and_resume_analysis(
    analysis_id: int,
    checkpoint_id: str,
    update_state: dict,
    current_user,
    task_id: str,
    db: AsyncSession,
) -> None:
    from backend.core.database import AsyncSessionLocal
    from backend.repositories.analysis import get_analysis_by_id
    from backend.repositories.system_settings import get_system_settings
    from backend.services.analysis.config_builder import build_analysis_config, prepare_graph_config
    from backend.services.settings_service import get_or_create_settings
    from backend.services.strategy_context_service import load_strategy_context
    from backend.trading_agents.graph.checkpointer import checkpoint_scope, get_async_checkpointer, thread_id
    from backend.trading_agents.graph.trading_graph import TradingAgentsGraph

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if analysis is None:
        raise ValueError("Analysis not found or access denied")

    settings = await get_or_create_settings(db, current_user)
    sys_settings = await get_system_settings(db)
    config = build_analysis_config(settings, user=current_user, sys_settings=sys_settings)
    config["trade_date"] = str(analysis.trade_date)
    config["historical_mode"] = True
    config["analysis_mode"] = "time_travel"
    config["learning_eligible"] = False
    config["allow_live_data_in_historical"] = False
    config["historical_context"] = (
        "=== POINT-IN-TIME MODE ===\n"
        f"Knowledge cutoff: {analysis.trade_date}. Live portfolio state, current market pulse, "
        "future outcome attribution, replay statistics, and current scenarios were excluded.\n\n"
    )
    config["strategy_context"] = await load_strategy_context(
        db,
        user_id=analysis.user_id,
        ticker=str(analysis.ticker),
        asset_type=str(analysis.asset_type),
        trade_date=str(analysis.trade_date),
        historical_mode=True,
        learning_eligible=False,
    )
    permitted_analysts = await prepare_graph_config(db, current_user.id if current_user else None, config)

    checkpoint_namespace = checkpoint_scope(analysis.user_id, analysis.id)
    config["checkpoint_scope"] = checkpoint_namespace

    ta = TradingAgentsGraph(selected_analysts=permitted_analysts, config=config)
    tid = thread_id(analysis.ticker, analysis.trade_date, checkpoint_namespace)
    node_name = "START"
    config_param = {"configurable": {"thread_id": tid}}

    async with get_async_checkpointer(config["data_cache_dir"], analysis.ticker, checkpoint_namespace) as saver:
        async for cp in saver.alist(config_param):
            if cp.config["configurable"]["checkpoint_id"] == checkpoint_id:
                metadata = cp.metadata or {}
                writes = metadata.get("writes") or {}
                node_name = next(iter(writes.keys()), "START") if writes else "START"
                break

    async with get_async_checkpointer(config["data_cache_dir"], analysis.ticker, checkpoint_namespace) as saver:
        graph = ta.workflow.compile(checkpointer=saver)
        update_config = {"configurable": {"thread_id": tid, "checkpoint_id": checkpoint_id}}
        safe_update_state = {
            **update_state,
            **_time_travel_checkpoint_overrides(
                strategy_context=config["strategy_context"],
                historical_context=config["historical_context"],
            ),
        }
        await graph.aupdate_state(update_config, safe_update_state, as_node=node_name)

    analysis.status = "running"
    analysis.task_id = task_id
    analysis.signal = None
    analysis.final_decision = ""
    await db.commit()

    await register_task_owner(task_id, current_user.id if current_user else None)

    resume_ticker = str(analysis.ticker)
    resume_trade_date = str(analysis.trade_date)
    resume_asset_type = str(analysis.asset_type)
    resume_user_id = current_user.id if current_user else None
    result_owner_user_id = analysis.user_id

    async def run_resume():
        if current_user:
            from backend.core.log_handler import current_user_id

            current_user_id.set(current_user.id)
        emitter = AnalysisEmitter(task_id)
        terminal_result = TerminalResult(AnalysisTaskStatus.COMPLETED)
        try:
            await _track_running_task(
                task_id,
                ticker=resume_ticker,
                trade_date=resume_trade_date,
                asset_type=resume_asset_type,
                user_id=resume_user_id,
            )
            async with AsyncSessionLocal() as session:
                if current_user is not None:
                    await set_user_background_context(session, current_user.id)
                try:
                    from backend.services.analysis.orchestrator import run_individual_analysis

                    await run_individual_analysis(
                        resume_ticker,
                        resume_trade_date,
                        resume_asset_type,
                        settings,
                        session,
                        emitter,
                        triggered_by="time-travel",
                        user=current_user,
                        checkpoint_namespace=checkpoint_namespace,
                        result_owner_user_id=result_owner_user_id,
                        existing_result_id=analysis_id,
                    )
                    await session.commit()
                except asyncio.CancelledError:
                    await session.rollback()
                    raise
                except Exception:
                    await session.rollback()
                    from backend.repositories.analysis import update_analysis_result

                    await update_analysis_result(session, analysis_id, status="failed")
                    raise
        except asyncio.CancelledError:
            terminal_result = TerminalResult(AnalysisTaskStatus.CANCELLED, reason="time-travel resume cancelled")
            await emitter.emit_error("Analysis resume was cancelled.")
            raise
        except Exception as exc:
            terminal_result = TerminalResult(AnalysisTaskStatus.FAILED, reason=type(exc).__name__)
            _logger.exception("Time-travel resume task failed task=%s", task_id)
            await emitter.emit_error("Analysis resume failed before completion.")
        finally:
            await terminalize_task(task_id, resume_user_id, terminal_result)
            await emitter.close()

    task = asyncio.create_task(run_resume())
    _RUNNING_TASKS[task_id] = task


async def list_analysis_checkpoints(analysis_id: int, db: AsyncSession, current_user) -> list[dict] | None:
    import os

    from backend.repositories.analysis import get_analysis_by_id
    from backend.trading_agents.default_config import DEFAULT_CONFIG
    from backend.trading_agents.graph.checkpointer import checkpoint_scope, list_checkpoints_for_thread

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if not analysis:
        return None

    data_cache_dir = os.environ.get("TRADINGAGENTS_DATA_CACHE_DIR", DEFAULT_CONFIG["data_cache_dir"])
    return await list_checkpoints_for_thread(
        data_cache_dir,
        analysis.ticker,
        analysis.trade_date,
        checkpoint_scope(analysis.user_id, analysis.id),
    )
