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


async def _mark_analysis_terminal(task_id: str, status: str, user_id: int | None) -> None:
    """Persist worker preparation failures for the pre-created queue row."""
    from datetime import UTC, datetime

    from sqlalchemy import update

    from backend.core.database import AsyncSessionLocal
    from backend.core.rls_context import set_user_background_context
    from backend.models.analysis import AnalysisResult

    try:
        async with AsyncSessionLocal() as db:
            if user_id is not None:
                await set_user_background_context(db, user_id)
            await db.execute(
                update(AnalysisResult)
                .where(AnalysisResult.task_id == task_id)
                .where(AnalysisResult.status.in_(("queued", "running")))
                .values(status=status, heartbeat_at=datetime.now(UTC), worker_id=None)
            )
            await db.commit()
    except Exception:
        _logger.exception("Could not persist terminal worker state task=%s status=%s", task_id, status)

async def run_analysis_job(
    ctx,
    ticker: str,
    trade_date: str,
    asset_type: str,
    user_id: int | None,
    task_id: str,
    triggered_by: str = "manual",
):
    from backend.core.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.services.analysis_service import run_analysis_task
    from backend.services.settings_service import get_or_create_settings

    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id) if user_id is not None else None
            if user_id is not None:
                from backend.core.rls_context import set_user_background_context
                await set_user_background_context(db, user_id)
            if user_id is not None and user is None:
                _logger.warning("Dropping analysis task=%s: owner user_id=%s no longer exists", task_id, user_id)
                from backend.core import task_store
                from backend.services.analysis.emitter import AnalysisEmitter

                emitter = AnalysisEmitter(task_id)
                await emitter.emit_error("Analysis owner no longer exists")
                await emitter.close()
                await task_store.clear_meta(task_id, user_id)
                await task_store.clear_owner(task_id)
                await task_store.clear_cancel_request(task_id)
                await _mark_analysis_terminal(task_id, "failed", user_id)
                return
            settings = await get_or_create_settings(db, user)
            await db.commit()

        await run_analysis_task(ticker, trade_date, asset_type, settings, task_id, user, triggered_by)
    except asyncio.CancelledError:
        _logger.info("Analysis worker job cancelled task=%s", task_id)
        from backend.core import task_store
        from backend.services.analysis.emitter import AnalysisEmitter

        try:
            emitter = AnalysisEmitter(task_id)
            await emitter.emit_error("Analysis cancelled.")
            await emitter.close()
            await _mark_analysis_terminal(task_id, "cancelled", user_id)
        finally:
            await task_store.clear_meta(task_id, user_id)
            await task_store.clear_owner(task_id)
            await task_store.clear_cancel_request(task_id)
        raise
    except Exception:
        _logger.exception("Analysis worker preparation failed task=%s", task_id)
        from backend.core import task_store
        from backend.services.analysis.emitter import AnalysisEmitter

        emitter = AnalysisEmitter(task_id)
        try:
            await emitter.emit_error("Analysis failed before execution. Please try again.")
            await _mark_analysis_terminal(task_id, "failed", user_id)
        finally:
            await emitter.close()
            await task_store.clear_meta(task_id, user_id)
            await task_store.clear_owner(task_id)
            await task_store.clear_cancel_request(task_id)

async def run_portfolio_job(
    ctx, tickers: list[str], trade_date: str, asset_type: str, user_id: int | None, task_id: str
):
    from backend.core.database import AsyncSessionLocal
    from backend.models.user import User
    from backend.services.analysis_service import run_portfolio_task
    from backend.services.settings_service import get_or_create_settings

    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id) if user_id is not None else None
            if user_id is not None:
                from backend.core.rls_context import set_user_background_context
                await set_user_background_context(db, user_id)
            if user_id is not None and user is None:
                _logger.warning("Dropping portfolio task=%s: owner user_id=%s no longer exists", task_id, user_id)
                from backend.core import task_store
                from backend.services.analysis.emitter import AnalysisEmitter

                emitter = AnalysisEmitter(task_id)
                await emitter.emit_error("Analysis owner no longer exists")
                await emitter.close()
                await task_store.clear_meta(task_id, user_id)
                await task_store.clear_owner(task_id)
                await task_store.clear_cancel_request(task_id)
                return
            settings = await get_or_create_settings(db, user)
            await db.commit()

        await run_portfolio_task(tickers, trade_date, asset_type, settings, user, task_id)
    except asyncio.CancelledError:
        _logger.info("Portfolio worker job cancelled task=%s", task_id)
        from backend.core import task_store
        from backend.services.analysis.emitter import AnalysisEmitter

        try:
            emitter = AnalysisEmitter(task_id)
            await emitter.emit_error("Portfolio analysis cancelled.")
            await emitter.close()
        finally:
            await task_store.clear_meta(task_id, user_id)
            await task_store.clear_owner(task_id)
            await task_store.clear_cancel_request(task_id)
        raise
    except Exception:
        _logger.exception("Portfolio worker preparation failed task=%s", task_id)
        from backend.core import task_store
        from backend.services.analysis.emitter import AnalysisEmitter

        emitter = AnalysisEmitter(task_id)
        try:
            await emitter.emit_error("Portfolio analysis failed before execution. Please try again.")
        finally:
            await emitter.close()
            await task_store.clear_meta(task_id, user_id)
            await task_store.clear_owner(task_id)
            await task_store.clear_cancel_request(task_id)

async def startup(ctx):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from backend.trading_agents.agents.runtime.logging_config import setup_unified_logging

    setup_unified_logging()
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    from backend.core.log_handler import db_log_handler
    from backend.core.task_store import control_listener
    from backend.services.analysis_service import cancel_local_task

    # Without this the whole worker process logs nowhere near the database, so
    # every queue-mode analysis is invisible on the System Logs page.
    await db_log_handler.start()

    ctx["control_listener"] = asyncio.create_task(control_listener(cancel_local_task))
    _logger.info("Analysis worker ready (queue mode).")

async def shutdown(ctx):
    listener = ctx.get("control_listener")
    if listener:
        listener.cancel()
    from backend.core.log_handler import db_log_handler
    from backend.core.redis_bus import close_redis

    db_log_handler.stop()
    await close_redis()

def _redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().REDIS_URL or "redis://localhost:6379/0")

class WorkerSettings:
    functions = [run_analysis_job, run_portfolio_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 1800
