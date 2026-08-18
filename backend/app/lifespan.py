import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core.config import get_settings
from backend.core.database import create_all_tables
from backend.core.log_handler import db_log_handler
from backend.services.cron_service import init_cron_service
from backend.startup.recovery import recover_lost_alerts, recover_stale_analyses, reset_interrupted_update

_logger = logging.getLogger(__name__)


async def _load_cron_settings(cron) -> None:
    try:
        from sqlalchemy import select

        from backend.core.rls_context import BackgroundCapability, trusted_background_session
        from backend.models.settings import AppSettings

        async with trusted_background_session(BackgroundCapability.CRON_BOOTSTRAP) as db:
            app_res = await db.execute(select(AppSettings).where(AppSettings.cron_enabled))
            for app_settings in app_res.scalars():
                await cron.apply_user_settings(app_settings)
    except Exception as exc:
        _logger.warning("Could not load cron settings: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("Starting TradingAgents Web API...")

    from backend.trading_agents.agents.runtime.logging_config import setup_unified_logging

    setup_unified_logging()
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401

    reset_interrupted_update()

    await create_all_tables()
    # No owner is seeded here. An installation with no users serves the
    # first-run setup screen, which registers the owner through /auth/setup.
    await recover_stale_analyses()
    await db_log_handler.start()
    await recover_lost_alerts()

    redis_tasks: list[asyncio.Task] = []
    from backend.core.redis_bus import redis_enabled

    settings = get_settings()
    if redis_enabled():
        from backend.core.event_bus import event_forwarder
        from backend.core.task_store import control_listener
        from backend.services.analysis_service import cancel_local_task

        redis_tasks.append(asyncio.create_task(event_forwarder()))
        redis_tasks.append(asyncio.create_task(control_listener(cancel_local_task)))
        _logger.info("Redis event bus active (queue mode: %s).", settings.ANALYSIS_QUEUE_MODE)

    cron = init_cron_service()
    await _load_cron_settings(cron)
    cron.start()
    _logger.info("Application ready.")
    yield
    cron.stop()

    for task in redis_tasks:
        task.cancel()

    from backend.services.alert_service import _BACKGROUND_TASKS
    from backend.services.analysis_service import _RUNNING_TASKS

    pending = list(_RUNNING_TASKS.values()) + list(_BACKGROUND_TASKS)
    if pending:
        _logger.info("Waiting for %d running background analysis/alert tasks...", len(pending))
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=15.0)
        except TimeoutError:
            _logger.warning("Timeout waiting for background tasks to complete during shutdown.")

    from backend.core.redis_bus import close_redis
    from backend.services.analysis_queue import close_arq_pool

    await close_arq_pool()
    await close_redis()

    _logger.info("Application stopped.")
    db_log_handler.stop()
