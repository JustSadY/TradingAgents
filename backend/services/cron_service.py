"""Scheduled background work, and the health record behind ``/api/cron/status``.

The scheduler is in-process and single-instance (``deploy/README.md`` forbids
``--workers``), so every job registration lives only in this process's memory.
Anything that drops one — a bootstrap that failed while the database was still
coming up, a settings event that removed a job without re-adding it, an advisory
lock left behind on a pooled connection — stopped that user's scans until
someone restarted the service, and nothing anywhere said so: the status endpoint
reported a latched ``running`` flag that was set once at startup and never
cleared.

Two mechanisms replace that silence:

* every scheduled run records its outcome (``ok``/``skipped``/``error``/
  ``missed``) with a reason, and a heartbeat only a live event loop can refresh
  proves the scheduler is still turning; ``/api/cron/status`` publishes both.
* :meth:`CronService.resync_user_jobs` rebuilds the per-user jobs from the
  stored settings on a timer, so a registration that goes missing is restored
  within one resync interval instead of waiting for a restart.
"""

import hashlib
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
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

#: Job-id prefix for the per-user watchlist scan.
USER_JOB_PREFIX = "watchlist_scan_user_"

DEFAULT_CRON_SCHEDULE = "0 9 * * 1-5"

#: How often the liveness heartbeat is refreshed, and how stale it may get
#: before the scheduler counts as stalled. APScheduler reports ``running`` from
#: the moment ``start()`` returns, so a wedged event loop still looks healthy;
#: a timestamp only a live loop can write is what distinguishes the two.
HEARTBEAT_INTERVAL_SECONDS = 60
HEARTBEAT_STALE_AFTER = timedelta(seconds=HEARTBEAT_INTERVAL_SECONDS * 3)

#: How often the stored cron settings are replayed onto the scheduler.
RESYNC_INTERVAL_MINUTES = 15


def user_job_id(user_id: int) -> str:
    return f"{USER_JOB_PREFIX}{user_id}"


def _advisory_lock_key(job_name: str) -> int:
    return int.from_bytes(hashlib.sha256(job_name.encode("utf-8")).digest()[:8], "big", signed=True)


@dataclass
class JobRun:
    """The most recent execution of one scheduled job.

    ``outcome`` is one of ``running``, ``ok``, ``skipped``, ``error`` or
    ``missed``; ``detail`` carries the human-readable reason so a skipped run
    can be told apart from a run that never happened at all.
    """

    started_at: datetime
    finished_at: datetime | None = None
    outcome: str = "running"
    detail: str | None = None


def _record_start(job_id: str) -> None:
    if _cron_service is not None:
        _cron_service.record_start(job_id)


def _record_outcome(job_id: str, outcome: str, detail: str | None = None) -> None:
    if _cron_service is not None:
        _cron_service.record_outcome(job_id, outcome, detail)


@asynccontextmanager
async def _job_lock(job_name: str):
    """Hold a PostgreSQL advisory lock for the duration of a scheduled job.

    Every web process owns its own APScheduler instance, so a database-scoped
    lock keeps interval and per-user cron jobs singleton when the application is
    deployed with multiple workers or replicas. SQLite remains a single-process
    development fallback.

    Advisory locks are session-scoped and survive ``ROLLBACK``, so a lock left
    behind on a connection that goes back into the pool makes every later run of
    the same job skip itself until the process restarts. A connection whose
    unlock fails is therefore invalidated instead of being reused, and a skip is
    logged at WARNING rather than DEBUG — in the supported single-process
    topology there is no second scheduler for it to be a duplicate of.
    """
    if engine.dialect.name != "postgresql":
        yield True
        return

    lock_key = _advisory_lock_key(job_name)
    try:
        conn = await engine.connect()
    except Exception as exc:
        _logger.warning("Scheduled job %s skipped: no database connection for its lock: %s", job_name, exc)
        _record_outcome(job_name, "skipped", f"database connection unavailable: {exc}")
        yield False
        return

    try:
        await conn.execute(text("SET statement_timeout = 0"))
        acquired = bool(
            (await conn.execute(text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": lock_key})).scalar()
        )
    except Exception as exc:
        _logger.warning("Scheduled job %s skipped: advisory lock could not be taken: %s", job_name, exc)
        _record_outcome(job_name, "skipped", f"advisory lock unavailable: {exc}")
        await _discard_lock_connection(conn, job_name)
        yield False
        return

    if not acquired:
        _logger.warning("Scheduled job %s skipped: its advisory lock is held by another session", job_name)
        _record_outcome(job_name, "skipped", "advisory lock held by another session")
        await _discard_lock_connection(conn, job_name)
        yield False
        return

    try:
        yield True
    finally:
        try:
            await conn.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": lock_key})
            await conn.close()
        except Exception as exc:
            _logger.warning(
                "Failed to release the advisory lock for %s; discarding the connection so the lock "
                "cannot outlive it in the pool: %s",
                job_name,
                exc,
            )
            await _discard_lock_connection(conn, job_name, invalidate=True)


async def _discard_lock_connection(conn, job_name: str, *, invalidate: bool = False) -> None:
    """Return a lock connection to the pool, or drop it if it may still hold one."""
    try:
        if invalidate:
            await conn.invalidate()
        await conn.close()
    except Exception as exc:
        _logger.warning("Failed to close the advisory-lock connection for %s: %s", job_name, exc)


async def _run_transient_cleanup():
    _record_start("transient_cleanup")
    async with _job_lock("transient_cleanup") as acquired:
        if not acquired:
            return
        from backend.services.maintenance_service import cleanup_transient_data

        counts = await cleanup_transient_data()
        if any(counts.values()):
            _logger.info("Transient-data cleanup removed rows: %s", counts)
        _record_outcome("transient_cleanup", "ok", f"removed rows: {counts}")


def _trade_date_for_asset(asset_type: str) -> str:
    timezone = ZoneInfo("UTC") if asset_type.lower() == "crypto" else ZoneInfo("America/New_York")
    return datetime.now(timezone).date().isoformat()


class CronService:
    def __init__(self):
        from backend.core.config import get_settings

        self.timezone = get_settings().APP_TIMEZONE
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self._started_at: datetime | None = None
        self._heartbeat_at: datetime | None = None
        self._bootstrap_error: str | None = None
        self._last_resync_at: datetime | None = None
        #: job id -> most recent run, so a status query can say *why* nothing ran.
        self._job_runs: dict[str, JobRun] = {}
        #: user id -> the schedule currently registered, so a resync only
        #: re-registers a job whose definition actually changed.
        self._user_schedules: dict[int, str] = {}

    # -- liveness -----------------------------------------------------------

    @property
    def running(self) -> bool:
        """Whether APScheduler itself is running, not whether it once started."""
        return bool(getattr(self.scheduler, "running", False))

    def mark_heartbeat(self) -> None:
        self._heartbeat_at = datetime.now(UTC)

    def record_start(self, job_id: str) -> None:
        self._job_runs[job_id] = JobRun(started_at=datetime.now(UTC))

    def record_outcome(self, job_id: str, outcome: str, detail: str | None = None) -> None:
        run = self._job_runs.get(job_id)
        now = datetime.now(UTC)
        if run is None:
            run = JobRun(started_at=now)
            self._job_runs[job_id] = run
        run.finished_at = now
        run.outcome = outcome
        run.detail = detail

    def _on_job_event(self, event) -> None:
        """Surface the APScheduler outcomes that otherwise never reach the UI."""
        job_id = getattr(event, "job_id", "unknown")
        if event.code == EVENT_JOB_MISSED:
            scheduled = getattr(event, "scheduled_run_time", None)
            _logger.warning("Scheduled job %s missed its run time (%s)", job_id, scheduled)
            self.record_outcome(job_id, "missed", f"missed its scheduled run at {scheduled}")
        elif event.code == EVENT_JOB_MAX_INSTANCES:
            _logger.warning("Scheduled job %s skipped: the previous run has not finished", job_id)
            self.record_outcome(job_id, "skipped", "the previous run has not finished")
        elif event.code == EVENT_JOB_ERROR:
            _logger.error("Scheduled job %s raised an exception: %s", job_id, getattr(event, "exception", None))
            self.record_outcome(job_id, "error", str(getattr(event, "exception", "unknown error")))

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        if self.running:
            return
        self.scheduler.start()
        self._started_at = datetime.now(UTC)
        self.mark_heartbeat()
        self.scheduler.add_listener(self._on_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)
        self.scheduler.add_job(
            _run_scheduler_heartbeat,
            "interval",
            seconds=HEARTBEAT_INTERVAL_SECONDS,
            id="scheduler_heartbeat",
            replace_existing=True,
            misfire_grace_time=HEARTBEAT_INTERVAL_SECONDS,
        )
        self.scheduler.add_job(
            _run_cron_resync,
            "interval",
            minutes=RESYNC_INTERVAL_MINUTES,
            id="cron_resync",
            replace_existing=True,
            misfire_grace_time=300,
        )
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
        if self.running:
            self.scheduler.shutdown(wait=False)
        self._heartbeat_at = None

    async def bootstrap(self) -> None:
        """Register the stored user jobs once the application is up.

        A failure here used to leave the process with no user job at all while
        the status endpoint still reported a healthy scheduler. It is recorded
        instead, and the periodic resync retries it.
        """
        try:
            await self.resync_user_jobs(reason="startup")
        except Exception as exc:
            self._bootstrap_error = str(exc)
            _logger.exception("Could not load cron settings at startup; the periodic resync will retry")

    # -- registration -------------------------------------------------------

    async def _username_for(self, user_id: int) -> str:
        """Best-effort username for log lines; falls back to the id.

        Opened with an explicit tenant context: a bare background session has
        no ``app.*`` settings, so the row-level-security policy denies the read
        and every log line would say ``user_id=N``.
        """
        try:
            from backend.core.rls_context import set_user_background_context

            async with AsyncSessionLocal() as db:
                await set_user_background_context(db, user_id)
                user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
                if user:
                    return user.username
        except Exception as exc:
            _logger.debug("Failed to fetch username for logging user_id=%s: %s", user_id, exc)
        return f"user_id={user_id}"

    async def apply_user_settings(self, settings):
        if not settings.user_id:
            return
        user_id = settings.user_id
        job_id = user_job_id(user_id)
        cron_enabled = bool(getattr(settings, "cron_enabled", False))
        cron_schedule = getattr(settings, "cron_schedule", DEFAULT_CRON_SCHEDULE) or DEFAULT_CRON_SCHEDULE
        watchlist = getattr(settings, "watchlist", []) or []
        username = await self._username_for(user_id)

        try:
            self.scheduler.remove_job(job_id)
        except JobLookupError:
            pass

        if not cron_enabled:
            self._user_schedules.pop(user_id, None)
            _logger.info("No cron job registered for user=%s: scheduled scans are disabled", username)
            return
        if not watchlist:
            # Silently dropping the job here is what made "cron stopped
            # working" indistinguishable from "cron is fine": the schedule is
            # still enabled in the UI while nothing is registered.
            self._user_schedules.pop(user_id, None)
            _logger.warning("No cron job registered for user=%s: cron is enabled but the watchlist is empty", username)
            return

        try:
            trigger = CronTrigger.from_crontab(cron_schedule, timezone=self.timezone)
            self.scheduler.add_job(
                self._run_user_watchlist_scan,
                trigger,
                args=[user_id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
            )
            self._user_schedules[user_id] = cron_schedule
        except Exception:
            self._user_schedules.pop(user_id, None)
            _logger.exception("Failed to configure user cron job for user=%s", username)
            return

        job = self.scheduler.get_job(job_id)
        next_run = getattr(job, "next_run_time", None) if job else None
        _logger.info(
            "User cron job configured for user=%s: %s (timezone=%s, next run=%s)",
            username,
            cron_schedule,
            self.timezone,
            next_run.isoformat() if next_run else "pending scheduler start",
        )

    async def resync_user_jobs(self, *, reason: str) -> int:
        """Replay the stored cron settings onto the scheduler.

        The registrations exist only in this process, so whatever loses one —
        a failed startup, an event handler that removed it, a scheduler that
        was restarted underneath — leaves the user with a schedule that never
        fires and no way to tell. Rebuilding from the database closes that gap
        without a restart. Returns how many missing jobs were restored.
        """
        from backend.core.rls_context import BackgroundCapability, trusted_background_session

        restored = 0
        enabled_user_ids: set[int] = set()

        # The rows stay attached for the whole replay: reading them after the
        # session closes would leave every lazy attribute unloadable.
        async with trusted_background_session(BackgroundCapability.CRON_BOOTSTRAP) as db:
            rows = list((await db.execute(select(AppSettings).where(AppSettings.cron_enabled))).scalars())

            for app_settings in rows:
                user_id = app_settings.user_id
                if not user_id:
                    continue
                enabled_user_ids.add(user_id)
                schedule = getattr(app_settings, "cron_schedule", DEFAULT_CRON_SCHEDULE) or DEFAULT_CRON_SCHEDULE
                watchlist = getattr(app_settings, "watchlist", []) or []
                registered = self.scheduler.get_job(user_job_id(user_id)) is not None

                if registered and self._user_schedules.get(user_id) == schedule:
                    continue
                if not registered and not watchlist:
                    # Nothing to restore: an empty watchlist has no job by
                    # design, and apply_user_settings already logged why.
                    continue
                if not registered and reason != "startup":
                    restored += 1
                    _logger.warning(
                        "Restoring a missing cron job for user_id=%s during the %s resync; "
                        "scheduled scans had stopped running for this user",
                        user_id,
                        reason,
                    )
                await self.apply_user_settings(app_settings)

        for job in list(self.scheduler.get_jobs()):
            if not job.id.startswith(USER_JOB_PREFIX):
                continue
            try:
                job_user_id = int(job.id[len(USER_JOB_PREFIX) :])
            except ValueError:
                continue
            if job_user_id not in enabled_user_ids:
                _logger.info("Removing cron job for user_id=%s: scheduled scans are no longer enabled", job_user_id)
                try:
                    self.scheduler.remove_job(job.id)
                except JobLookupError:
                    pass
                self._user_schedules.pop(job_user_id, None)

        self._bootstrap_error = None
        self._last_resync_at = datetime.now(UTC)
        return restored

    # -- the scheduled scan -------------------------------------------------

    async def _run_user_watchlist_scan(self, user_id: int):
        job_id = user_job_id(user_id)
        self.record_start(job_id)
        async with _job_lock(job_id) as acquired:
            if not acquired:
                return
            await self._run_user_watchlist_scan_once(user_id)

    async def _run_user_watchlist_scan_once(self, user_id: int):
        from backend.core.log_handler import current_user_id

        job_id = user_job_id(user_id)
        current_user_id.set(user_id)
        async with AsyncSessionLocal() as db:
            from backend.core.rls_context import set_user_background_context

            await set_user_background_context(db, user_id)
            u_res = await db.execute(select(User).where(User.id == user_id))
            user = u_res.scalar_one_or_none()
            if not user or not user.is_active:
                _logger.warning("User with id=%d not found or inactive, skipping cron scan", user_id)
                self.record_outcome(job_id, "skipped", "the account is missing or inactive")
                return
            app_res = await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))
            app_settings = app_res.scalar_one_or_none()
            if not app_settings or not app_settings.cron_enabled:
                self.record_outcome(job_id, "skipped", "scheduled scans are disabled in settings")
                return

            trade_date = _trade_date_for_asset("stock")
            username = user.username

            # A holiday scan spends a full analysis run per ticker on quotes
            # that cannot move, and any signal it produces feeds automation
            # that could not be filled anyway.
            closed = market_closed_reason(date.fromisoformat(trade_date), asset_type="stock")
            if closed:
                _logger.info("Skipping cron watchlist scan for user=%s: %s", username, closed)
                self.record_outcome(job_id, "skipped", closed)
                return

            _logger.info(
                "User cron watchlist scan started for user=%s (id=%d), date=%s",
                username,
                user_id,
                trade_date,
            )
            from uuid import uuid4

            from backend.repositories.analysis import create_analysis_result
            from backend.services.analysis_queue import dispatch_analysis
            from backend.services.analysis_service import register_queued_task

            queued = 0
            failed = 0
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
                        None,
                        ticker=ticker,
                        trade_date=trade_date,
                        asset_type="stock",
                        settings=app_settings,
                        task_id=task_id,
                        user=user,
                        triggered_by="cron",
                    )
                    queued += 1
                except Exception:
                    failed += 1
                    _logger.exception("User cron scan failed for user=%s, ticker=%s", username, ticker)
                    await db.rollback()
                    from backend.repositories.analysis import update_analysis_result
                    from backend.services.analysis_service import clear_task_owner

                    if queued_row is not None:
                        await update_analysis_result(db, queued_row.id, status="failed", heartbeat_at=datetime.now(UTC))
                    await clear_task_owner(task_id)
            _logger.info("User cron watchlist scan completed for user=%s (id=%d)", username, user_id)
            self.record_outcome(
                job_id,
                "error" if failed and not queued else "ok",
                f"queued {queued} ticker(s), {failed} failed",
            )

    # -- status -------------------------------------------------------------

    def get_status(self, user_id: int | None = None) -> dict:
        """The in-process half of the status: scheduler liveness and this job."""
        now = datetime.now(UTC)
        heartbeat_age = (now - self._heartbeat_at).total_seconds() if self._heartbeat_at else None
        status: dict = {
            "running": self.running,
            "timezone": str(self.timezone),
            "started_at": _iso(self._started_at),
            "last_heartbeat_at": _iso(self._heartbeat_at),
            "heartbeat_age_seconds": heartbeat_age,
            "last_resync_at": _iso(self._last_resync_at),
            "job_configured": False,
            "next_run_time": None,
            "last_run_at": None,
            "schedule": None,
            "last_outcome": None,
            "last_outcome_at": None,
            "last_outcome_detail": None,
            "degraded_reason": None,
            "degraded_detail": self._bootstrap_error,
        }

        if not self.running:
            status["degraded_reason"] = "scheduler_stopped"
        elif heartbeat_age is not None and heartbeat_age > HEARTBEAT_STALE_AFTER.total_seconds():
            status["degraded_reason"] = "scheduler_stalled"
            status["degraded_detail"] = f"no heartbeat for {int(heartbeat_age)}s"
        elif self._bootstrap_error:
            status["degraded_reason"] = "bootstrap_failed"

        if not user_id:
            return status

        job = self.scheduler.get_job(user_job_id(user_id))
        status["job_configured"] = job is not None
        status["schedule"] = self._user_schedules.get(user_id)
        next_run = getattr(job, "next_run_time", None) if job else None
        status["next_run_time"] = next_run.isoformat() if next_run else None

        run = self._job_runs.get(user_job_id(user_id))
        if run is not None:
            status["last_outcome"] = run.outcome
            status["last_outcome_at"] = _iso(run.finished_at or run.started_at)
            status["last_outcome_detail"] = run.detail
        return status

    async def build_status(self, db, user_id: int | None = None) -> dict:
        """Full status: scheduler liveness plus what the database remembers.

        ``last_run_at`` comes from the analyses the scan actually queued, so it
        survives the restart that clears every in-process counter — the one
        number that answers "did this run at all in the last few days?".
        """
        status = self.get_status(user_id=user_id)
        if not user_id:
            return status

        status["last_run_at"] = _iso(await _last_cron_analysis_at(db, user_id))
        if status["degraded_reason"] is None and not status["job_configured"]:
            enabled = await _cron_enabled_for(db, user_id)
            if enabled:
                status["degraded_reason"] = "job_missing"
                status["degraded_detail"] = (
                    "scheduled scans are enabled but no job is registered; "
                    f"the scheduler re-registers it within {RESYNC_INTERVAL_MINUTES} minutes"
                )
        return status


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _last_cron_analysis_at(db, user_id: int) -> datetime | None:
    from backend.models.analysis import AnalysisResult

    try:
        return (
            await db.execute(
                select(AnalysisResult.created_at)
                .where(AnalysisResult.user_id == user_id, AnalysisResult.triggered_by == "cron")
                .order_by(AnalysisResult.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    except Exception as exc:
        _logger.warning("Could not read the last cron-triggered analysis for user_id=%s: %s", user_id, exc)
        return None


async def _cron_enabled_for(db, user_id: int) -> bool:
    try:
        return bool(
            (
                await db.execute(select(AppSettings.cron_enabled).where(AppSettings.user_id == user_id))
            ).scalar_one_or_none()
        )
    except Exception as exc:
        _logger.warning("Could not read the cron setting for user_id=%s: %s", user_id, exc)
        return False


async def _run_scheduler_heartbeat():
    """Refresh the liveness timestamp. Deliberately touches nothing else."""
    if _cron_service is not None:
        _cron_service.mark_heartbeat()


async def _run_cron_resync():
    if _cron_service is None:
        return
    try:
        restored = await _cron_service.resync_user_jobs(reason="periodic")
        if restored:
            _logger.warning("Cron resync restored %d missing user job(s)", restored)
    except Exception:
        _logger.exception("Cron resync failed; scheduled user scans may be missing")


async def _run_alert_checker():
    _record_start("alert_checker")
    try:
        async with _job_lock("alert_checker") as acquired:
            if acquired:
                await check_price_alerts()
                _record_outcome("alert_checker", "ok")
    except Exception as exc:
        _logger.exception("Alert checker error")
        _record_outcome("alert_checker", "error", str(exc))


async def _run_performance_backfill():
    _record_start("perf_backfill")
    try:
        async with _job_lock("perf_backfill") as acquired:
            if not acquired:
                return
            from backend.core.rls_context import BackgroundCapability, trusted_background_session

            async with trusted_background_session(BackgroundCapability.PERFORMANCE_BACKFILL) as db:
                await backfill_returns(db)
            _record_outcome("perf_backfill", "ok")
    except Exception as exc:
        _logger.exception("Performance backfill error")
        _record_outcome("perf_backfill", "error", str(exc))


async def _run_position_monitor():
    """Periodically enforce stop-loss / take-profit / liquidation on open positions.

    The exchange-holiday gate lives per holding in ``mock_trading_service`` so a
    crypto position keeps being monitored while its equity neighbours wait for
    the next session.
    """
    _record_start("position_monitor")
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
            _record_outcome("position_monitor", "ok", f"closed {len(closed)} position(s)" if closed else None)
    except Exception as exc:
        _logger.exception("Position monitor error")
        _record_outcome("position_monitor", "error", str(exc))


def init_cron_service() -> CronService:
    global _cron_service
    _cron_service = CronService()

    from backend.core.events import subscribe

    subscribe("settings_updated", _cron_service.apply_user_settings)

    def _on_user_deleted(user_id: int):
        job_id = user_job_id(user_id)
        try:
            _cron_service.scheduler.remove_job(job_id)
            _logger.info("Successfully removed watchlist scan cron job for deleted user %d", user_id)
        except JobLookupError:
            pass
        _cron_service._user_schedules.pop(user_id, None)

    subscribe("user_deleted", _on_user_deleted)

    return _cron_service


def get_cron_service() -> CronService | None:
    return _cron_service
