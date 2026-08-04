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
import time
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import task_store
from backend.core.database import AsyncSessionLocal
from backend.models.settings import AppSettings
from backend.services.execution.base import OrderResult
from backend.services.trading_orchestrator import auto_execute_signals_enabled, place_signal_order

from .analysis.emitter import AnalysisEmitter

from .analysis.orchestrator import run_individual_analysis
from .analysis.portfolio_orchestrator import run_portfolio_analysis

_logger = logging.getLogger(__name__)

_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_TASK_REGISTRY: dict[str, dict] = {}
_TASK_OWNERS: dict[str, int | None] = {}

async def register_task_owner(task_id: str, user_id: int | None) -> None:
    _TASK_OWNERS[task_id] = user_id
    await task_store.set_owner(task_id, user_id)

async def clear_task_owner(task_id: str) -> None:
    _TASK_OWNERS.pop(task_id, None)
    await task_store.clear_owner(task_id)

async def is_task_owner(task_id: str, user_id: int | None, is_admin: bool = False) -> bool:
    """Return True if *user* may subscribe to *task_id*'s event stream.

    Admins may observe any task. Otherwise the task must have a known owner that
    matches the user; unknown task ids are rejected so a stream can only be
    reached via a task id the server actually issued to that user.
    """
    if is_admin:
        return True
    owner = _TASK_OWNERS.get(task_id)
    if owner is None:
        owner = await task_store.get_owner(task_id)
    return owner is not None and owner == user_id

async def cancel_local_task(task_id: str) -> bool:
    """Cancel ``task_id`` if it is running in THIS process."""
    task = _RUNNING_TASKS.get(task_id)
    if task and not task.done():
        task.cancel()
        return True
    return False

async def cancel_analysis(task_id: str) -> bool:
    """Cancel a run wherever it is executing.

    Persist intent before the best-effort local/pub-sub signals.  Pub/sub is
    transient, so a worker that has not started yet must be able to observe
    the request when it begins.
    """
    await task_store.request_cancel(task_id)
    await cancel_local_task(task_id)
    await task_store.publish_cancel(task_id)
    return True

async def get_active_tasks_for_user(user_id: int | None) -> list[dict]:
    """Returns a list of active tasks for the given user (all processes)."""
    tasks = [{"task_id": tid, **meta} for tid, meta in _TASK_REGISTRY.items() if meta.get("user_id") == user_id]
    if user_id is not None:
        seen = {t["task_id"] for t in tasks}
        tasks.extend(t for t in await task_store.list_tasks_for_user(user_id) if t["task_id"] not in seen)
    return tasks

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
    existing = await task_store.get_meta(task_id) or {}
    meta = {
        "ticker": ticker,
        "trade_date": trade_date,
        "asset_type": asset_type,
        "user_id": user_id,
        "started_at": time.time(),
        "status": "running",
        "retry_count": existing.get("retry_count", 0),
    }
    _RUNNING_TASKS[task_id] = current
    _TASK_REGISTRY[task_id] = meta
    await task_store.set_meta(task_id, meta)
    await register_task_owner(task_id, user_id)

async def _clear_terminal_task_state(task_id: str, user_id: int | None) -> None:
    """Remove tracking only after the runner reached a terminal state."""
    _RUNNING_TASKS.pop(task_id, None)
    _TASK_REGISTRY.pop(task_id, None)
    await task_store.clear_meta(task_id, user_id)
    await clear_task_owner(task_id)
    await task_store.clear_cancel_request(task_id)

async def _emit_cancelled_task(task_id: str, *, close: bool = True) -> None:
    """Tell subscribers about a pre-start or portfolio cancellation.

    ``run_analysis_task`` can defer the close while it is unwinding a
    cancelled database operation.  That preserves the important wire order:
    subscribers receive the terminal ``error`` event before the socket is
    closed.  Other callers retain the one-shot emit-and-close behaviour.
    """
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
    """Emit a post-analysis order outcome without making it a second analysis.

    The report is already complete when this runs.  Keep an execution failure
    separate from the analysis terminal event: otherwise a valid report looks
    like it either filled an order or failed entirely.
    """
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
    """Copy order inputs before committing so expired ORM rows are never read.

    SQLAlchemy may expire ``AnalysisResult`` attributes at commit time.  The
    automatic order is deliberately a later transaction, therefore it must
    work from plain values rather than accidentally lazy-loading through a
    cancelled or rolled-back session.
    """
    return SimpleNamespace(
        id=getattr(row, "id", None),
        signal=getattr(row, "signal", None),
        quality=getattr(row, "quality", None),
        chart_annotations=getattr(row, "chart_annotations", None),
        portfolio_decision_json=getattr(row, "portfolio_decision_json", None),
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
    """Facade for individual analysis orchestration.

    A background runner has work after the graph returns (the final commit and
    optional signal order).  It passes ``defer_terminal_cleanup=True`` so the
    task stays cancellable and its WebSocket remains open until that outer
    runner has emitted/handled the terminal outcome.  Direct callers keep the
    historical self-contained lifecycle by default.
    """
    import uuid

    if task_id is None:
        task_id = str(uuid.uuid4())

    user_id = user.id if user else None
    emitter = AnalysisEmitter(task_id)
    try:
        if await task_store.is_cancel_requested(task_id):
            await emitter.emit_error("Analysis cancelled.")
            raise asyncio.CancelledError

        await _track_running_task(
            task_id,
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            user_id=user_id,
        )
        if await task_store.is_cancel_requested(task_id):
            await emitter.emit_error("Analysis cancelled.")
            raise asyncio.CancelledError
        return await run_individual_analysis(ticker, trade_date, asset_type, settings, db, emitter, triggered_by, user)
    except Exception as exc:
        if getattr(emitter, "terminal_event_emitted", False):
            exc._analysis_terminal_event_emitted = True
        raise
    finally:
        if not defer_terminal_cleanup:
            await _clear_terminal_task_state(task_id, user_id)
            await emitter.close()

async def run_analysis_task(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    task_id: str,
    user=None,
) -> None:
    """Background entrypoint for a manual analysis run."""
    if user:
        from backend.core.log_handler import current_user_id

        current_user_id.set(user.id)
    retry_scheduled = False
    analysis_completed = False
    async with AsyncSessionLocal() as db:
        try:
            _, row = await run_analysis(
                ticker,
                trade_date,
                asset_type,
                settings,
                db,
                "manual",
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
                await _clear_terminal_task_state(task_id, user.id if user else None)
                return
            analysis_completed = True
            emitter = AnalysisEmitter(task_id)

            if await task_store.is_cancel_requested(task_id):
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
                    if await task_store.is_cancel_requested(task_id):
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
            await _clear_terminal_task_state(task_id, user.id if user else None)
        except asyncio.CancelledError:
            _logger.info("Background analysis cancelled task=%s", task_id)
            try:
                await db.commit()
            except Exception:
                await db.rollback()
                _logger.exception("Could not persist cancelled analysis task=%s", task_id)
            await _clear_terminal_task_state(task_id, user.id if user else None)
            raise
        except Exception as exc:
            if await task_store.is_cancel_requested(task_id):
                _logger.info("Background analysis stopped during failure cleanup task=%s", task_id)
                await db.rollback()
                await _emit_cancelled_task(task_id, close=False)
                await _clear_terminal_task_state(task_id, user.id if user else None)
                return
            if analysis_completed or getattr(exc, "_analysis_terminal_event_emitted", False):
                _logger.info("Not retrying analysis with an emitted terminal event task=%s", task_id)
                await _clear_terminal_task_state(task_id, user.id if user else None)
                return
            _logger.exception("Background analysis failed")
            try:
                retry_scheduled = await _maybe_retry_analysis(ticker, trade_date, asset_type, settings, task_id, user)
            except Exception:
                _logger.exception("Analysis retry failed for task=%s", task_id)
            if not retry_scheduled:
                if await task_store.is_cancel_requested(task_id):
                    await _emit_cancelled_task(task_id, close=False)
                else:
                    await AnalysisEmitter(task_id).emit_error("Analysis failed before completion. Please try again.")
                await _clear_terminal_task_state(task_id, user.id if user else None)
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
    """Return False to ensure failed tasks are not automatically re-enqueued.

    Failed tasks are cleared immediately from the task registry so that a page
    refresh or opening from a new tab does not restart or re-attach to a failed run.
    """
    return False

async def run_portfolio_task(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    user=None,
    task_id: str | None = None,
) -> None:
    """Background entrypoint for a multi-ticker portfolio analysis run."""
    if user:
        from backend.core.log_handler import current_user_id

        current_user_id.set(user.id)
    user_id = user.id if user else None
    try:
        if task_id:
            if await task_store.is_cancel_requested(task_id):
                await _emit_cancelled_task(task_id)
                return
            await _track_running_task(
                task_id,
                ticker=", ".join(tickers),
                trade_date=trade_date,
                asset_type=asset_type,
                user_id=user_id,
            )
            if await task_store.is_cancel_requested(task_id):
                raise asyncio.CancelledError

        async with AsyncSessionLocal() as db:
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
        _logger.info("Portfolio analysis cancelled task=%s", task_id)
        if task_id:
            await _emit_cancelled_task(task_id)
        raise
    except Exception:
        _logger.exception("Portfolio analysis failed")
        if task_id:
            emitter = AnalysisEmitter(task_id)
            await emitter.emit_error("Portfolio analysis failed")
            await emitter.close()
    finally:
        if task_id:
            await _clear_terminal_task_state(task_id, user_id)

async def rollback_and_resume_analysis(
    analysis_id: int,
    checkpoint_id: str,
    update_state: dict,
    current_user,
    task_id: str,
    db: AsyncSession,
) -> None:
    """Rollback analysis to a specific checkpoint, update the state, and resume execution in the background."""
    import time

    from backend.core.database import AsyncSessionLocal
    from backend.repositories.analysis import get_analysis_by_id
    from backend.repositories.system_settings import get_system_settings
    from backend.services.analysis.config_builder import build_analysis_config, prepare_graph_config
    from backend.services.settings_service import get_or_create_settings
    from backend.trading_agents.graph.checkpointer import checkpoint_scope, get_async_checkpointer, thread_id
    from backend.trading_agents.graph.trading_graph import TradingAgentsGraph

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if analysis is None:
        raise ValueError("Analysis not found or access denied")

    settings = await get_or_create_settings(db, current_user)
    sys_settings = await get_system_settings(db)
    config = build_analysis_config(settings, user=current_user, sys_settings=sys_settings)
    from backend.core.temporal import is_historical_trade_date

    config["trade_date"] = str(analysis.trade_date)
    config["historical_mode"] = is_historical_trade_date(str(analysis.trade_date))
    config["allow_live_data_in_historical"] = False
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
        await graph.aupdate_state(update_config, update_state, as_node=node_name)

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
        try:
            await _track_running_task(
                task_id,
                ticker=resume_ticker,
                trade_date=resume_trade_date,
                asset_type=resume_asset_type,
                user_id=resume_user_id,
            )
            async with AsyncSessionLocal() as session:
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
            await emitter.emit_error("Analysis resume was cancelled.")
            raise
        except Exception:
            _logger.exception("Time-travel resume task failed task=%s", task_id)
            await emitter.emit_error("Analysis resume failed before completion.")
        finally:
            await _clear_terminal_task_state(task_id, resume_user_id)
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
