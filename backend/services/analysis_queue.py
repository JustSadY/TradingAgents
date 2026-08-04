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
import logging

from backend.core.config import get_settings

_logger = logging.getLogger(__name__)

_arq_pool = None
_INLINE_TASKS: set[asyncio.Task] = set()

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
    if queue_mode() == "worker":
        pool = await get_arq_pool()
        await pool.enqueue_job(
            "run_analysis_job", ticker, trade_date, asset_type, user.id if user else None, task_id, triggered_by
        )
        return
    from backend.services.analysis_service import run_analysis_task

    if background_tasks is not None:
        background_tasks.add_task(
            run_analysis_task, ticker, trade_date, asset_type, settings, task_id, user, triggered_by
        )
    else:
        task = asyncio.create_task(
            run_analysis_task(ticker, trade_date, asset_type, settings, task_id, user, triggered_by)
        )
        _INLINE_TASKS.add(task)
        task.add_done_callback(_INLINE_TASKS.discard)

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
