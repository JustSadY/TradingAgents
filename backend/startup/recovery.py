import logging

_logger = logging.getLogger(__name__)


def reset_interrupted_update() -> None:
    from backend.services.update_service import reset_stuck_update

    reset_stuck_update()


async def recover_stale_analyses() -> None:
    from backend.core.rls_context import BackgroundCapability, trusted_background_session
    from backend.repositories.analysis import cleanup_stale_analyses

    try:
        async with trusted_background_session(BackgroundCapability.STARTUP_CLEANUP) as db:
            count = await cleanup_stale_analyses(db)
            if count > 0:
                _logger.info("Marked %d stale analyses as failed.", count)
    except Exception as exc:
        _logger.warning("Failed to cleanup stale analyses on startup: %s", exc)


async def recover_lost_alerts() -> None:
    from backend.services.alert_service import check_and_recover_lost_alerts

    try:
        await check_and_recover_lost_alerts()
    except Exception as exc:
        _logger.warning("Failed to recover lost alerts: %s", exc)
