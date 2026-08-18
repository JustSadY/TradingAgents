"""The scheduled watchlist scan does not burn analysis runs on closed days."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import delete

from backend.core.database import AsyncSessionLocal
from backend.core.password_hashing import hash_password
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.services import cron_service

NYSE_HOLIDAY = "2026-07-03"
NYSE_SESSION = "2026-07-06"


@pytest_asyncio.fixture
async def cron_user(test_engine):
    """A committed user + cron settings; the scan opens its own session."""
    async with AsyncSessionLocal() as db:
        user = User(username="cron-owner", hashed_password=hash_password("cron-pass-123"), role="user")
        db.add(user)
        await db.flush()
        settings = AppSettings(user_id=user.id, cron_enabled=True)
        settings.watchlist = ["AAPL", "MSFT"]
        db.add(settings)
        await db.commit()
        user_id = user.id

    yield user_id

    async with AsyncSessionLocal() as db:
        await db.execute(delete(AppSettings).where(AppSettings.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.fixture
def captured_dispatches(monkeypatch):
    """Record what the scan would have queued, without running any analysis."""
    dispatched: list[str] = []

    async def fake_create_analysis_result(_db, **kwargs):
        return None

    async def fake_register_queued_task(_task_id, **_kwargs):
        return None

    async def fake_dispatch(_background, *, ticker, **_kwargs):
        dispatched.append(ticker)

    from backend.repositories import analysis as analysis_repo
    from backend.services import analysis_queue, analysis_service

    monkeypatch.setattr(analysis_repo, "create_analysis_result", fake_create_analysis_result)
    monkeypatch.setattr(analysis_service, "register_queued_task", fake_register_queued_task)
    monkeypatch.setattr(analysis_queue, "dispatch_analysis", fake_dispatch)
    return dispatched


class TestCronExchangeCalendar:
    async def test_no_tickers_are_queued_on_an_exchange_holiday(
        self, cron_user, captured_dispatches, monkeypatch
    ):
        monkeypatch.setattr(cron_service, "_trade_date_for_asset", lambda _asset: NYSE_HOLIDAY)

        await cron_service.CronService()._run_user_watchlist_scan_once(cron_user)

        assert captured_dispatches == []

    async def test_the_whole_watchlist_is_queued_on_a_session_day(
        self, cron_user, captured_dispatches, monkeypatch
    ):
        monkeypatch.setattr(cron_service, "_trade_date_for_asset", lambda _asset: NYSE_SESSION)

        await cron_service.CronService()._run_user_watchlist_scan_once(cron_user)

        assert captured_dispatches == ["AAPL", "MSFT"]
