import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text

from backend.core.database import AsyncSessionLocal, engine
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.services.alert_service import check_price_alerts
from backend.services.market_calendar_service import market_closed_reason
from backend.services.performance_service import backfill_returns

_logger = logging.getLogger(__name__)
_cron_service: Optional["CronService"] = None

@asynccontextmanager
async def _job_lock(job_name: str):
    """Acquire a PostgreSQL advisory lock for a scheduler job.

    Every web process owns its own APScheduler instance.  A database-scoped
    lock keeps interval and per-user cron jobs singleton when the application
    is deployed with multiple workers or replicas.  SQLite remains a
    single-process development fallback.
    """
    if engine.dialect.name != "postgresql":
        yield True
        return

    import hashlib

    lock_key = int.from_bytes(hashlib.sha256(job_name.encode("utf-8")).digest()[:8], "big", signed=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET statement_timeout = 0"))
            acquired = bool(
                (await conn.execute(text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": lock_key})).scalar()
            )
            if not acquired:
                _logger.debug("Skipping duplicate scheduled job: %s", job_name)
                yield False
                return
            try:
                yield True
            finally:
                try:
                    await conn.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key})
                except Exception as exc:
                    _logger.warning("Failed to release advisory lock for %s: %s", job_name, exc)
    except Exception as exc:
        _logger.warning("Advisory lock execution error for %s: %s", job_name, exc)
        yield False


async def _run_transient_cleanup():
    async with _job_lock("transient_cleanup") as acquired:
        if not acquired:
            return
        from backend.services.maintenance_service import cleanup_transient_data

        counts = await cleanup_transient_data()
        if any(counts.values()):
            _logger.info("Transient-data cleanup removed rows: %s", counts)

def _trade_date_for_asset(asset_type: str) -> str:
    timezone = ZoneInfo("UTC") if asset_type.lower() == "crypto" else ZoneInfo("America/New_York")
    return datetime.now(timezone).date().isoformat()


class CronService:
    def __init__(self):
        from backend.core.config import get_settings

        self.timezone = get_settings().APP_TIMEZONE
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self._running = False

    def start(self):
        if not self._running:
            self.scheduler.start()
            self._running = True
            self.scheduler.add_job(
                _run_alert_checker,
                "interval",
                minutes=5,
                id="alert_checker",
                replace_existing=True,
                misfire_grace_time=60,
            )
            self.scheduler.add_job(
                _run_performance_backfill,
                "interval",
                hours=6,
                id="perf_backfill",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            self.scheduler.add_job(
                _run_position_monitor,
                "interval",
                minutes=5,
                id="position_monitor",
                replace_existing=True,
                misfire_grace_time=120,
            )
            self.scheduler.add_job(
                _run_transient_cleanup,
                "interval",
                hours=24,
                id="transient_cleanup",
                replace_existing=True,
                misfire_grace_time=3600,
            )
            _logger.info("CronService started")

    def stop(self):
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False

    async def apply_user_settings(self, settings):
        if not settings.user_id:
            return
        job_id = f"watchlist_scan_user_{settings.user_id}"
        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass
        cron_enabled = getattr(settings, "cron_enabled", False)
        cron_schedule = getattr(settings, "cron_schedule", "0 9 * * 1-5") or "0 9 * * 1-5"
        watchlist = getattr(settings, "watchlist", [])
        username = f"user_id={settings.user_id}"
        try:
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(User).where(User.id == settings.user_id))
                user = res.scalar_one_or_none()
                if user:
                    username = user.username
        except Exception as e:
            _logger.debug("Failed to fetch username for logging user_id=%s: %s", settings.user_id, e)
        if cron_enabled and watchlist:
            try:
                trigger = CronTrigger.from_crontab(cron_schedule, timezone=self.timezone)
                self.scheduler.add_job(
                    self._run_user_watchlist_scan,
                    trigger,
                    args=[settings.user_id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=300,
                )
                _logger.info("User cron job configured for user=%s: %s", username, cron_schedule)
            except Exception:
                _logger.exception("Failed to configure user cron job for user=%s", username)

    async def _run_user_watchlist_scan(self, user_id: int):
        async with _job_lock(f"watchlist_scan_user_{user_id}") as acquired:
            if not acquired:
                return
            await self._run_user_watchlist_scan_once(user_id)

    async def _run_user_watchlist_scan_once(self, user_id: int):
        from backend.core.log_handler import current_user_id

        current_user_id.set(user_id)
        async with AsyncSessionLocal() as db:
            from backend.core.rls_context import set_user_background_context

            await set_user_background_context(db, user_id)
            u_res = await db.execute(select(User).where(User.id == user_id))
            user = u_res.scalar_one_or_none()
            if not user or not user.is_active:
                _logger.warning("User with id=%d not found or inactive, skipping cron scan", user_id)
                return
            app_res = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
            app_settings = app_res.scalar_one_or_none()
            if not app_settings or not app_settings.cron_enabled:
                return

            trade_date = _trade_date_for_asset("stock")
            username = user.username

            # A holiday scan spends a full analysis run per ticker on quotes
            # that cannot move, and any signal it produces feeds automation
            # that could not be filled anyway.
            closed = market_closed_reason(date.fromisoformat(trade_date), asset_type="stock")
            if closed:
                _logger.info("Skipping cron watchlist scan for user=%s: %s", username, closed)
                return

            _logger.info(
                "User cron watchlist scan started for user=%s (id=%d), date=%s",
                username, user_id, trade_date,
            )
            from uuid import uuid4

            from backend.repositories.analysis import create_analysis_result
            from backend.services.analysis_queue import dispatch_analysis
            from backend.services.analysis_service import register_queued_task

            for ticker in app_settings.watchlist:
                task_id = str(uuid4())
                queued_row = None
                try:
                    _logger.info("User=%s queueing ticker=%s", username, ticker)
                    queued_row = await create_analysis_result(
                        db,
                        task_id=task_id,
                        user_id=user.id,
                        ticker=ticker,
                        trade_date=trade_date,
                        asset_type="stock",
                        status="queued",
                        heartbeat_at=datetime.now(UTC),
                        triggered_by="cron",
                    )
                    await db.commit()
                    await register_queued_task(
                        task_id, ticker=ticker, trade_date=trade_date, asset_type="stock", user_id=user.id
                    )
                    await dispatch_analysis(
                        None, ticker=ticker, trade_date=trade_date, asset_type="stock",
                        settings=app_settings, task_id=task_id, user=user, triggered_by="cron",
                    )
                except Exception:
                    _logger.exception("User cron scan failed for user=%s, ticker=%s", username, ticker)
                    await db.rollback()
                    from backend.repositories.analysis import update_analysis_result
                    from backend.services.analysis_service import clear_task_owner
                    if queued_row is not None:
                        await update_analysis_result(
                            db, queued_row.id, status="failed", heartbeat_at=datetime.now(UTC)
                        )
                    await clear_task_owner(task_id)
            _logger.info("User cron watchlist scan completed for user=%s (id=%d)", username, user_id)

    def get_status(self, user_id: int | None = None) -> dict:
        if not user_id:
            return {"running": self._running, "job_configured": False, "next_run_time": None}
        job_id = f"watchlist_scan_user_{user_id}"
        job = self.scheduler.get_job(job_id)
        return {
            "running": self._running,
            "job_configured": job is not None,
            "next_run_time": job.next_run_time.isoformat() if job and job.next_run_time else None,
        }

async def _run_alert_checker():
    try:
        async with _job_lock("alert_checker") as acquired:
            if acquired:
                await check_price_alerts()
    except Exception:
        _logger.exception("Alert checker error")

async def _run_performance_backfill():
    try:
        async with _job_lock("perf_backfill") as acquired:
            if not acquired:
                return
            from backend.core.rls_context import BackgroundCapability, trusted_background_session

            async with trusted_background_session(BackgroundCapability.PERFORMANCE_BACKFILL) as db:
                await backfill_returns(db)
    except Exception:
        _logger.exception("Performance backfill error")

async def _run_position_monitor():
    """Periodically enforce stop-loss / take-profit / liquidation on open positions.

    The exchange-holiday gate lives per holding in ``mock_trading_service`` so a
    crypto position keeps being monitored while its equity neighbours wait for
    the next session.
    """
    try:
        async with _job_lock("position_monitor") as acquired:
            if not acquired:
                return
            from backend.core.rls_context import BackgroundCapability, trusted_background_session
            from backend.services.mock_trading_service import monitor_open_positions

            async with trusted_background_session(BackgroundCapability.POSITION_MONITOR) as db:
                closed = await monitor_open_positions(db)
                await db.commit()
                if closed:
                    _logger.info("Position monitor auto-closed %d position(s): %s", len(closed), closed)
    except Exception:
        _logger.exception("Position monitor error")

def init_cron_service() -> CronService:
    global _cron_service
    _cron_service = CronService()

    from backend.core.events import subscribe

    subscribe("settings_updated", _cron_service.apply_user_settings)

    def _on_user_deleted(user_id: int):
        job_id = f"watchlist_scan_user_{user_id}"
        try:
            _cron_service.scheduler.remove_job(job_id)
            _logger.info("Successfully removed watchlist scan cron job for deleted user %d", user_id)
        except JobLookupError:
            pass

    subscribe("user_deleted", _on_user_deleted)

    return _cron_service

def get_cron_service() -> CronService | None:
    return _cron_service
