"""arq worker running analysis jobs out of the web process.

Start with:
    arq backend.worker.WorkerSettings

Requires ``REDIS_URL`` in ``.env``; the web process must run with
``ANALYSIS_QUEUE_MODE=worker`` so /api/analysis/run enqueues here instead of
executing inline. Analysis WebSocket events flow back to web-process clients
via the Redis event bus, and cancel requests arrive on the control channel.
"""

import asyncio
import logging

import backend.bootstrap  # noqa: F401  (engine env defaults; import before trading_agents)
from backend.core.config import get_settings

_logger = logging.getLogger(__name__)


async def run_analysis_job(ctx, ticker: str, trade_date: str, asset_type: str, user_id: int | None, task_id: str):
    from backend.core.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.services.analysis_service import run_analysis_task
    from backend.services.settings_service import get_or_create_settings

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id) if user_id is not None else None
        settings = await get_or_create_settings(db, user)
        await db.commit()

    await run_analysis_task(ticker, trade_date, asset_type, settings, task_id, user)


async def run_portfolio_job(
    ctx, tickers: list[str], trade_date: str, asset_type: str, user_id: int | None, task_id: str
):
    from backend.core.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.services.analysis_service import run_portfolio_task
    from backend.services.settings_service import get_or_create_settings

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id) if user_id is not None else None
        settings = await get_or_create_settings(db, user)
        await db.commit()

    await run_portfolio_task(tickers, trade_date, asset_type, settings, user, task_id)


async def startup(ctx):  # NOSONAR
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    # Register tools so analyst plugins resolve, same as the web process.
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    from backend.core.task_store import control_listener
    from backend.services.analysis_service import cancel_local_task

    ctx["control_listener"] = asyncio.create_task(control_listener(cancel_local_task))
    _logger.info("Analysis worker ready (queue mode).")


async def shutdown(ctx):
    listener = ctx.get("control_listener")
    if listener:
        listener.cancel()
    from backend.core.redis_bus import close_redis

    await close_redis()


def _redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().REDIS_URL or "redis://localhost:6379/0")


class WorkerSettings:
    functions = [run_analysis_job, run_portfolio_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # LLM-heavy graph runs: keep per-worker concurrency low and allow long jobs.
    max_jobs = 4
    job_timeout = 1800
