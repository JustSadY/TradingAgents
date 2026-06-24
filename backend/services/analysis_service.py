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

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import task_store
from backend.core.database import AsyncSessionLocal
from backend.models.settings import AppSettings
from backend.services.trading_orchestrator import place_signal_order

from .analysis.emitter import AnalysisEmitter

# Sub-module imports
from .analysis.orchestrator import run_individual_analysis
from .analysis.portfolio_orchestrator import run_portfolio_analysis

_logger = logging.getLogger(__name__)

# In-process task tracking — the source of truth for runs executing in THIS
# process. With REDIS_URL set, ``task_store`` mirrors ownership and metadata to
# Redis so other processes (web vs. arq worker) can see and cancel them too.
_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_TASK_REGISTRY: dict[str, dict] = {}  # Re-used by get_active_tasks_for_user

# Maps an analysis task_id to the id of the user who started it. Populated
# by the API handlers before the task_id is returned to the client, so the
# WebSocket endpoint can verify ownership before streaming a run's
# reports/decisions to a connecting socket.
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
        # The run may have been registered by another process (arq worker mode).
        owner = await task_store.get_owner(task_id)
    return owner is not None and owner == user_id


async def cancel_local_task(task_id: str) -> bool:
    """Cancel ``task_id`` if it is running in THIS process."""
    task = _RUNNING_TASKS.pop(task_id, None)
    meta = _TASK_REGISTRY.pop(task_id, None)
    _TASK_OWNERS.pop(task_id, None)
    await task_store.clear_meta(task_id, (meta or {}).get("user_id"))
    await task_store.clear_owner(task_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def cancel_analysis(task_id: str) -> bool:
    """Cancel a run wherever it is executing.

    Cancels locally when the task lives in this process; otherwise broadcasts a
    cancel request on the control channel for the owning process to act on.
    """
    ran_here = task_id in _RUNNING_TASKS
    cancelled = await cancel_local_task(task_id)
    if not ran_here:
        await task_store.publish_cancel(task_id)
    return cancelled


async def get_active_tasks_for_user(user_id: int | None) -> list[dict]:
    """Returns a list of active tasks for the given user (all processes)."""
    tasks = [{"task_id": tid, **meta} for tid, meta in _TASK_REGISTRY.items() if meta.get("user_id") == user_id]
    if user_id is not None:
        seen = {t["task_id"] for t in tasks}
        tasks.extend(t for t in await task_store.list_tasks_for_user(user_id) if t["task_id"] not in seen)
    return tasks


async def run_analysis(
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    task_id: str | None = None,
    user=None,
):
    """Facade for individual analysis orchestration."""
    import time
    import uuid

    if task_id is None:
        task_id = str(uuid.uuid4())

    user_id = user.id if user else None
    current = asyncio.current_task()
    if current:
        meta = {
            "ticker": ticker,
            "trade_date": trade_date,
            "asset_type": asset_type,
            "user_id": user_id,
            "started_at": time.time(),
            "status": "running",
        }
        _RUNNING_TASKS[task_id] = current
        _TASK_REGISTRY[task_id] = meta
        await task_store.set_meta(task_id, meta)
        # Record ownership for runs that don't pass through the API handler
        # (alert-/cron-triggered), so their owner can still reconnect via WS.
        await register_task_owner(task_id, user_id)

    emitter = AnalysisEmitter(task_id)
    try:
        return await run_individual_analysis(ticker, trade_date, asset_type, settings, db, emitter, triggered_by, user)
    finally:
        _RUNNING_TASKS.pop(task_id, None)
        _TASK_REGISTRY.pop(task_id, None)
        _TASK_OWNERS.pop(task_id, None)
        await task_store.clear_meta(task_id, user_id)
        await task_store.clear_owner(task_id)
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
            )
            # Signal-based paper trading
            try:
                await place_signal_order(db, ticker=ticker, row=row, settings=settings, user=user)
                await db.commit()
            except Exception as exc:
                _logger.warning("Order execution skipped for %s: %s", ticker, exc)
                await db.rollback()
        except Exception:
            _logger.exception("Background analysis failed")
            await db.rollback()


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
    async with AsyncSessionLocal() as db:
        try:
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
        except Exception:
            _logger.exception("Portfolio analysis failed")
            await db.rollback()
            if task_id:
                # Surface the failure on the WebSocket channel so a subscribed
                # client stops waiting instead of hanging on an open socket.
                from backend.services.analysis.emitter import AnalysisEmitter

                emitter = AnalysisEmitter(task_id)
                await emitter.emit_error("Portfolio analysis failed")
                await emitter.close()
        finally:
            if task_id:
                await clear_task_owner(task_id)


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
    from backend.repositories.analysis import get_analysis_by_id, get_system_settings
    from backend.services.analysis.config_builder import build_analysis_config, prepare_graph_config
    from backend.services.settings_service import get_or_create_settings
    from backend.trading_agents.graph.checkpointer import get_async_checkpointer, thread_id
    from backend.trading_agents.graph.trading_graph import TradingAgentsGraph

    # 1. Fetch analysis and verify access
    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if analysis is None:
        raise ValueError("Analysis not found or access denied")

    # 2. Get user and system settings
    settings = await get_or_create_settings(db, current_user)
    sys_settings = await get_system_settings(db)
    config = build_analysis_config(settings, user=current_user, sys_settings=sys_settings)
    permitted_analysts = await prepare_graph_config(db, current_user.id if current_user else None, config)

    # 3. Resolve the target node name from checkpoint_id
    ta = TradingAgentsGraph(selected_analysts=permitted_analysts, config=config)
    tid = thread_id(analysis.ticker, analysis.trade_date)
    node_name = "START"
    config_param = {"configurable": {"thread_id": tid}}

    async with get_async_checkpointer(config["data_cache_dir"], analysis.ticker) as saver:
        async for cp in saver.alist(config_param):
            if cp.config["configurable"]["checkpoint_id"] == checkpoint_id:
                metadata = cp.metadata or {}
                writes = metadata.get("writes") or {}
                node_name = next(iter(writes.keys()), "START") if writes else "START"
                break

    # 4. Save the updated state on the selected checkpoint (this creates a new checkpoint fork)
    async with get_async_checkpointer(config["data_cache_dir"], analysis.ticker) as saver:
        graph = ta.workflow.compile(checkpointer=saver)
        update_config = {"configurable": {"thread_id": tid, "checkpoint_id": checkpoint_id}}
        await graph.aupdate_state(update_config, update_state, as_node=node_name)

    # 5. Update database record status back to running for progressive updates
    analysis.status = "running"
    analysis.task_id = task_id
    analysis.signal = None
    analysis.final_decision = ""
    await db.commit()

    # 6. Register task owner and spawn background task to resume graph execution
    await register_task_owner(task_id, current_user.id if current_user else None)

    async def run_resume():
        if current_user:
            from backend.core.log_handler import current_user_id

            current_user_id.set(current_user.id)
        async with AsyncSessionLocal() as session:
            try:
                from backend.services.analysis.emitter import AnalysisEmitter
                from backend.services.analysis.orchestrator import run_individual_analysis

                emitter = AnalysisEmitter(task_id)
                current_task = asyncio.current_task()
                if current_task:
                    _RUNNING_TASKS[task_id] = current_task
                    _TASK_REGISTRY[task_id] = {
                        "ticker": analysis.ticker,
                        "trade_date": analysis.trade_date,
                        "asset_type": analysis.asset_type,
                        "user_id": current_user.id if current_user else None,
                        "started_at": time.time(),
                        "status": "running",
                    }

                try:
                    await run_individual_analysis(
                        analysis.ticker,
                        analysis.trade_date,
                        analysis.asset_type,
                        settings,
                        session,
                        emitter,
                        triggered_by="time-travel",
                        user=current_user,
                    )
                    # Place order if signal triggers
                    try:
                        # Fetch the updated row
                        from backend.repositories.analysis import get_analysis_by_id as _get_row

                        updated_row = await _get_row(session, analysis_id, user=current_user)
                        if updated_row:
                            await place_signal_order(
                                session, ticker=analysis.ticker, row=updated_row, settings=settings, user=current_user
                            )
                            await session.commit()
                    except Exception as order_exc:
                        _logger.warning("Order execution skipped on time-travel resume: %s", order_exc)
                        await session.rollback()
                finally:
                    _RUNNING_TASKS.pop(task_id, None)
                    _TASK_REGISTRY.pop(task_id, None)
                    await clear_task_owner(task_id)
                    await emitter.close()
            except Exception:
                _logger.exception("Time-travel resume task failed")

    task = asyncio.create_task(run_resume())
    _RUNNING_TASKS[task_id] = task
