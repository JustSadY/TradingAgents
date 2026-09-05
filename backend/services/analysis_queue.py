"""Dispatch analysis runs inline (BackgroundTasks) or to the arq worker.

``ANALYSIS_QUEUE_MODE=inline`` (default) preserves the original behaviour:
the run executes inside the web process via FastAPI ``BackgroundTasks``.

``ANALYSIS_QUEUE_MODE=worker`` enqueues the run onto arq (Redis) instead, so
LLM-heavy graph execution happens in a separate ``backend.worker`` process.
ORM objects are not serialized across the queue — jobs carry only primitive
identifiers and the worker re-loads the user and settings from the database.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from backend.core.config import get_settings

_logger = logging.getLogger(__name__)

_arq_pool = None
_INLINE_TASKS: set[asyncio.Task] = set()
_INLINE_ANALYSIS_TASKS: dict[str, asyncio.Task] = {}


def queue_mode() -> str:
    return get_settings().ANALYSIS_QUEUE_MODE.strip().lower()


async def get_arq_pool():
    global _arq_pool
    if _arq_pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _arq_pool = await create_pool(RedisSettings.from_dsn(get_settings().REDIS_URL))
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        from backend.core.redis_bus import close_pool_or_client

        await close_pool_or_client(_arq_pool, _logger, "arq pool")
        _arq_pool = None


def _forget_inline_analysis(task_id: str, task: asyncio.Task) -> None:
    _INLINE_TASKS.discard(task)
    if _INLINE_ANALYSIS_TASKS.get(task_id) is task:
        _INLINE_ANALYSIS_TASKS.pop(task_id, None)


def _alert_task_id(*, user_id: int, ticker: str, trade_date: str) -> str:
    """Stable queue identity for one user's alert analysis on one trade date.

    Alert recovery already treats ``(ticker, trade_date, user_id)`` as the
    durable identity of an alert-triggered analysis. Use the same identity for
    dispatch so an outbox retry cannot manufacture a second analysis job.
    """
    raw = f"{user_id}:{ticker.strip().upper()}:{trade_date}".encode()
    return f"alert-{hashlib.sha256(raw).hexdigest()[:40]}"


async def _prepare_alert_dispatch_identity(
    *,
    task_id: str,
    ticker: str,
    trade_date: str,
    asset_type: str,
    user,
) -> tuple[str, bool]:
    """Canonicalize a freshly staged alert row before external queue I/O.

    ``create_analysis_result`` commits the queued row before dispatch. If an
    alert outbox item is retried, older code generated a fresh UUID and could
    therefore create and dispatch a duplicate analysis. Select the oldest row
    for the same recovery identity as canonical; only that row may dispatch.

    The first row is renamed to a deterministic task id before queue I/O. The
    random task-store registration created by the caller is replaced with the
    same deterministic id so Redis/arq, inline dispatch, DB persistence and
    recovery all agree on one identity.
    """
    if user is None:
        return task_id, True

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from backend.core.database import AsyncSessionLocal
    from backend.core.rls_context import set_user_background_context
    from backend.models.analysis import AnalysisResult
    from backend.services.analysis_service import discard_queued_task, register_queued_task

    stable_task_id = _alert_task_id(user_id=user.id, ticker=ticker, trade_date=trade_date)
    if task_id == stable_task_id:
        return task_id, True

    should_dispatch = True
    async with AsyncSessionLocal() as db:
        await set_user_background_context(db, user.id)
        rows = list(
            (
                await db.execute(
                    select(AnalysisResult)
                    .where(
                        AnalysisResult.user_id == user.id,
                        AnalysisResult.ticker == ticker.upper(),
                        AnalysisResult.trade_date == trade_date,
                        AnalysisResult.triggered_by == "alert",
                    )
                    .order_by(AnalysisResult.id.asc())
                )
            )
            .scalars()
            .all()
        )
        current = next((row for row in rows if row.task_id == task_id), None)
        canonical = rows[0] if rows else current

        if canonical is not None and current is not None and canonical.id != current.id:
            # The outbox is retrying work that already has a durable analysis
            # row. Remove only this newly staged duplicate; the canonical job
            # remains untouched regardless of whether it is queued, running,
            # completed or terminally failed.
            await db.delete(current)
            await db.commit()
            should_dispatch = False
        elif current is not None:
            current.task_id = stable_task_id
            try:
                await db.commit()
            except IntegrityError:
                # A concurrent outbox delivery won the deterministic task-id
                # race. Its row is canonical; remove this random duplicate.
                await db.rollback()
                current = (
                    await db.execute(select(AnalysisResult).where(AnalysisResult.task_id == task_id))
                ).scalar_one_or_none()
                if current is not None:
                    await db.delete(current)
                    await db.commit()
                should_dispatch = False

    await discard_queued_task(task_id, user.id)
    if not should_dispatch:
        _logger.info(
            "Skipping duplicate alert analysis dispatch user=%s ticker=%s trade_date=%s",
            user.id,
            ticker,
            trade_date,
        )
        return stable_task_id, False

    await register_queued_task(
        stable_task_id,
        ticker=ticker,
        trade_date=trade_date,
        asset_type=asset_type,
        user_id=user.id,
    )
    return stable_task_id, True


async def _cleanup_failed_alert_dispatch(task_id: str, user) -> None:
    """Remove a queued alert row when queue submission itself never succeeded."""
    if user is None:
        return

    from sqlalchemy import delete

    from backend.core.database import AsyncSessionLocal
    from backend.core.rls_context import set_user_background_context
    from backend.models.analysis import AnalysisResult
    from backend.services.analysis_service import discard_queued_task

    async with AsyncSessionLocal() as db:
        await set_user_background_context(db, user.id)
        await db.execute(
            delete(AnalysisResult).where(
                AnalysisResult.task_id == task_id,
                AnalysisResult.user_id == user.id,
                AnalysisResult.triggered_by == "alert",
                AnalysisResult.status == "queued",
            )
        )
        await db.commit()
    await discard_queued_task(task_id, user.id)


async def dispatch_analysis(
    background_tasks,
    *,
    ticker: str,
    trade_date: str,
    asset_type: str,
    settings,
    task_id: str,
    user,
    triggered_by: str = "manual",
) -> None:
    if triggered_by == "alert":
        task_id, should_dispatch = await _prepare_alert_dispatch_identity(
            task_id=task_id,
            ticker=ticker,
            trade_date=trade_date,
            asset_type=asset_type,
            user=user,
        )
        if not should_dispatch:
            return

    try:
        if queue_mode() == "worker":
            pool = await get_arq_pool()
            # arq de-duplicates jobs by _job_id. The analysis task id is already
            # globally unique and durable in AnalysisResult, so use the same
            # value for queue identity as well. A retry may safely call dispatch
            # again without creating a second worker execution.
            await pool.enqueue_job(
                "run_analysis_job",
                ticker,
                trade_date,
                asset_type,
                user.id if user else None,
                task_id,
                triggered_by,
                _job_id=task_id,
            )
            return
        from backend.services.analysis_service import run_analysis_task

        if background_tasks is not None:
            # FastAPI BackgroundTasks does not expose a durable task handle.
            # Alert calls have already been canonicalized above, so an outbox
            # retry is suppressed before reaching this branch.
            background_tasks.add_task(
                run_analysis_task, ticker, trade_date, asset_type, settings, task_id, user, triggered_by
            )
        else:
            existing = _INLINE_ANALYSIS_TASKS.get(task_id)
            if existing is not None and not existing.done():
                _logger.info("Skipping duplicate inline analysis dispatch task=%s", task_id)
                return
            task = asyncio.create_task(
                run_analysis_task(ticker, trade_date, asset_type, settings, task_id, user, triggered_by)
            )
            _INLINE_TASKS.add(task)
            _INLINE_ANALYSIS_TASKS[task_id] = task
            task.add_done_callback(lambda done, tid=task_id: _forget_inline_analysis(tid, done))
    except Exception:
        # A failed *submission* is different from a failed analysis. No worker
        # owns the queued row yet, so delete it and its task-store lease. The
        # durable alert outbox can then retry cleanly with the same identity.
        if triggered_by == "alert":
            await _cleanup_failed_alert_dispatch(task_id, user)
        raise


async def dispatch_portfolio_analysis(
    background_tasks,
    *,
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings,
    task_id: str,
    user,
) -> None:
    if queue_mode() == "worker":
        pool = await get_arq_pool()
        await pool.enqueue_job("run_portfolio_job", tickers, trade_date, asset_type, user.id if user else None, task_id)
        return
    from backend.services.analysis_service import run_portfolio_task

    if background_tasks is not None:
        background_tasks.add_task(run_portfolio_task, tickers, trade_date, asset_type, settings, user, task_id)
    else:
        task = asyncio.create_task(run_portfolio_task(tickers, trade_date, asset_type, settings, user, task_id))
        _INLINE_TASKS.add(task)
        task.add_done_callback(_INLINE_TASKS.discard)
