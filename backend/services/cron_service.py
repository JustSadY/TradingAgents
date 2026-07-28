import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text

from backend.core.database import AsyncSessionLocal, engine
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.services.alert_service import check_price_alerts
from backend.services.analysis_service import run_analysis
from backend.services.performance_service import backfill_returns
from backend.services.trading_orchestrator import is_actionable, place_signal_order

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


class CronService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
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
                trigger = CronTrigger.from_crontab(cron_schedule, timezone="UTC")
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
        today = date.today().strftime("%Y-%m-%d")
        async with AsyncSessionLocal() as db:
            u_res = await db.execute(select(User).where(User.id == user_id))
            user = u_res.scalar_one_or_none()
            if not user or not user.is_active:
                _logger.warning("User with id=%d not found or inactive, skipping cron scan", user_id)
                return
            _logger.info("User cron watchlist scan started for user=%s (id=%d), date=%s", user.username, user_id, today)
            app_res = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
            app_settings = app_res.scalar_one_or_none()
            if not app_settings or not app_settings.cron_enabled:
                return

            for ticker in app_settings.watchlist:
                try:
                    _logger.info("User=%s scanning ticker=%s", user.username, ticker)
                    task_id, row = await run_analysis(
                        ticker=ticker,
                        trade_date=today,
                        asset_type="stock",
                        settings=app_settings,
                        user=user,
                        db=db,
                        triggered_by="cron",
                    )
                    await db.commit()
                    await _place_actionable_signal_order(
                        db,
                        ticker=ticker,
                        row=row,
                        settings=app_settings,
                        user=user,
                    )
                except Exception:
                    _logger.exception("User cron scan failed for user=%s, ticker=%s", user.username, ticker)
                    await db.rollback()
            _logger.info("User cron watchlist scan completed for user=%s (id=%d)", user.username, user_id)

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


async def _place_actionable_signal_order(db, *, ticker: str, row, settings, user) -> bool:
    """Place cron orders through the orchestrator's single signal mapping."""
    if not is_actionable(getattr(row, "signal", None)):
        return False
    await place_signal_order(db, ticker=ticker, row=row, settings=settings, user=user)
    await db.commit()
    return True


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
            async with AsyncSessionLocal() as db:
                await backfill_returns(db)
    except Exception:
        _logger.exception("Performance backfill error")


async def _run_position_monitor():
    """Periodically enforce stop-loss / take-profit / liquidation on open positions."""
    try:
        async with _job_lock("position_monitor") as acquired:
            if not acquired:
                return
            from backend.services.mock_trading_service import monitor_open_positions

            async with AsyncSessionLocal() as db:
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
