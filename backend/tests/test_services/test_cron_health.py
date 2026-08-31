"""The scheduler has to be able to say whether it is actually working.

A schedule that quietly stops firing looked exactly like one that is fine: the
status endpoint published a boolean latched at startup, and every way a job can
disappear — a failed bootstrap, an empty watchlist, a lock held elsewhere — was
either silent or logged below the level that reaches the database.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import delete, select

from backend.core.database import AsyncSessionLocal
from backend.core.password_hashing import hash_password
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.services import cron_service
from backend.services.cron_service import CronService, user_job_id


@pytest_asyncio.fixture
async def scheduled_user(test_engine):
    """A user whose watchlist scan is enabled, committed for the scan's own session."""
    async with AsyncSessionLocal() as db:
        user = User(username="cron-health-owner", hashed_password=hash_password("cron-pass-123"), role="user")
        db.add(user)
        await db.flush()
        settings = AppSettings(user_id=user.id, cron_enabled=True, cron_schedule="0 9 * * 1-5")
        settings.watchlist = ["AAPL"]
        db.add(settings)
        await db.commit()
        user_id = user.id

    yield user_id

    async with AsyncSessionLocal() as db:
        await db.execute(delete(AppSettings).where(AppSettings.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest_asyncio.fixture
async def cron(test_engine):
    """A started scheduler, torn down so it cannot outlive the test.

    ``AsyncIOScheduler.start()`` binds to the running loop, so this has to be
    an async fixture.
    """
    service = CronService()
    service.start()
    yield service
    service.stop()


async def _settings_for(db, user_id: int) -> AppSettings:
    """The settings row for *user_id* — ``AppSettings`` is keyed by its own id."""
    return (await db.execute(select(AppSettings).where(AppSettings.user_id == user_id))).scalar_one()


class TestSchedulerLiveness:
    async def test_running_tracks_the_scheduler_rather_than_a_startup_latch(self, test_engine):
        service = CronService()
        assert service.running is False

        service.start()
        assert service.running is True

        service.stop()
        # APScheduler 3.11 defers the AsyncIO scheduler's shutdown onto the
        # loop, so the state flips one turn later.
        await asyncio.sleep(0)
        assert service.running is False

    async def test_a_stale_heartbeat_reports_a_stalled_scheduler(self, cron):
        cron.mark_heartbeat()
        assert cron.get_status()["degraded_reason"] is None

        cron._heartbeat_at = datetime.now(UTC) - (cron_service.HEARTBEAT_STALE_AFTER + timedelta(seconds=5))
        status = cron.get_status()

        assert status["running"] is True
        assert status["degraded_reason"] == "scheduler_stalled"

    async def test_a_stopped_scheduler_is_reported_as_stopped(self, test_engine):
        service = CronService()
        service.start()
        service.stop()
        await asyncio.sleep(0)

        assert service.get_status()["degraded_reason"] == "scheduler_stopped"


class TestJobRegistration:
    async def test_an_enabled_schedule_with_an_empty_watchlist_registers_nothing(self, cron, scheduled_user, caplog):
        async with AsyncSessionLocal() as db:
            settings = await _settings_for(db, scheduled_user)
            settings.watchlist = []
            await db.commit()

            with caplog.at_level("WARNING"):
                await cron.apply_user_settings(settings)

        assert cron.scheduler.get_job(user_job_id(scheduled_user)) is None
        assert "watchlist is empty" in caplog.text

    async def test_a_job_lost_from_the_scheduler_is_restored_by_the_resync(self, cron, scheduled_user):
        await cron.resync_user_jobs(reason="startup")
        assert cron.scheduler.get_job(user_job_id(scheduled_user)) is not None

        cron.scheduler.remove_job(user_job_id(scheduled_user))
        cron._user_schedules.pop(scheduled_user, None)

        restored = await cron.resync_user_jobs(reason="periodic")

        assert restored == 1
        assert cron.scheduler.get_job(user_job_id(scheduled_user)) is not None

    async def test_the_resync_drops_a_job_whose_owner_turned_scans_off(self, cron, scheduled_user):
        await cron.resync_user_jobs(reason="startup")
        assert cron.scheduler.get_job(user_job_id(scheduled_user)) is not None

        async with AsyncSessionLocal() as db:
            settings = await _settings_for(db, scheduled_user)
            settings.cron_enabled = False
            await db.commit()

        await cron.resync_user_jobs(reason="periodic")

        assert cron.scheduler.get_job(user_job_id(scheduled_user)) is None

    async def test_a_failed_bootstrap_leaves_the_scheduler_up_and_says_so(self, cron, monkeypatch):
        async def explode(**_kwargs):
            raise RuntimeError("database is starting up")

        monkeypatch.setattr(cron, "resync_user_jobs", explode)

        await cron.bootstrap()

        status = cron.get_status()
        assert cron.running is True
        assert status["degraded_reason"] == "bootstrap_failed"
        assert "database is starting up" in status["degraded_detail"]


class TestStatusReporting:
    async def test_an_enabled_schedule_with_no_registered_job_is_reported_as_missing(self, cron, scheduled_user):
        async with AsyncSessionLocal() as db:
            status = await cron.build_status(db, user_id=scheduled_user)

        assert status["job_configured"] is False
        assert status["degraded_reason"] == "job_missing"

    async def test_a_registered_job_reports_its_schedule_and_next_run(self, cron, scheduled_user):
        await cron.resync_user_jobs(reason="startup")

        async with AsyncSessionLocal() as db:
            status = await cron.build_status(db, user_id=scheduled_user)

        assert status["job_configured"] is True
        assert status["degraded_reason"] is None
        assert status["schedule"] == "0 9 * * 1-5"
        assert status["next_run_time"]

    async def test_a_skipped_run_records_why_it_was_skipped(self, cron, scheduled_user, monkeypatch):
        monkeypatch.setattr(cron_service, "market_closed_reason", lambda *_a, **_k: "NYSE holiday")

        await cron._run_user_watchlist_scan_once(scheduled_user)

        status = cron.get_status(user_id=scheduled_user)
        assert status["last_outcome"] == "skipped"
        assert status["last_outcome_detail"] == "NYSE holiday"

    async def test_a_completed_run_records_what_it_queued(self, cron, scheduled_user, monkeypatch):
        monkeypatch.setattr(cron_service, "market_closed_reason", lambda *_a, **_k: None)

        from backend.repositories import analysis as analysis_repo
        from backend.services import analysis_queue, analysis_service

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr(analysis_repo, "create_analysis_result", _noop)
        monkeypatch.setattr(analysis_service, "register_queued_task", _noop)
        monkeypatch.setattr(analysis_queue, "dispatch_analysis", _noop)

        await cron._run_user_watchlist_scan_once(scheduled_user)

        status = cron.get_status(user_id=scheduled_user)
        assert status["last_outcome"] == "ok"
        assert "queued 1 ticker(s)" in status["last_outcome_detail"]

    async def test_an_apscheduler_miss_is_recorded_against_the_job(self, cron, scheduled_user):
        from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent

        scheduled_for = datetime.now(UTC)
        cron._on_job_event(
            JobExecutionEvent(EVENT_JOB_MISSED, user_job_id(scheduled_user), "default", scheduled_for)
        )

        status = cron.get_status(user_id=scheduled_user)
        assert status["last_outcome"] == "missed"
        assert "missed its scheduled run" in status["last_outcome_detail"]
