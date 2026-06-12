"""Tests for price-alert sweeping (``alert_service.check_price_alerts``)."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.alert import PriceAlert
from backend.models.analysis import AnalysisResult  # noqa: F401 — register table
from backend.models.user import User
from backend.services import alert_service as svc


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def env(session_factory, monkeypatch):
    """Seed a user + stub the service's external dependencies."""
    async with session_factory() as db:
        user = User(username="alice", hashed_password="x", role="user")
        db.add(user)
        await db.commit()
        user_id = user.id

    state = SimpleNamespace(
        user_id=user_id,
        prices={},
        notifications=[],
        analyses=[],
        sys_settings=SimpleNamespace(),  # truthy -> notifications enabled
        session_factory=session_factory,
    )

    async def fake_prices(tickers):
        return {t: state.prices.get(t) for t in tickers if t in state.prices}

    async def fake_notify(ticker, condition, target_price, settings, alert_type="price"):
        state.notifications.append((ticker, condition, float(target_price), alert_type))

    async def fake_settings(db, u):
        return SimpleNamespace(owner_id=getattr(u, "id", None))

    async def fake_sys_settings(db):
        return state.sys_settings

    async def fake_analyze(ticker, trade_date, user_id, semaphore):
        state.analyses.append((ticker, trade_date, user_id))

    monkeypatch.setattr(svc, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(svc, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(svc, "notify_alert_triggered", fake_notify)
    monkeypatch.setattr(svc, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(svc, "_throttled_analyze", fake_analyze)

    import backend.repositories.analysis as analysis_repo

    monkeypatch.setattr(analysis_repo, "get_system_settings", fake_sys_settings)
    return state


async def _add_alert(session_factory, user_id, **kwargs):
    base = {"ticker": "AAPL", "condition": "above", "target_price": Decimal("150"), "enabled": True, "user_id": user_id}
    base.update(kwargs)
    async with session_factory() as db:
        alert = PriceAlert(**base)
        db.add(alert)
        await db.commit()
        return alert.id


async def _get_alert(session_factory, alert_id):
    async with session_factory() as db:
        return await db.get(PriceAlert, alert_id)


@pytest.mark.asyncio
async def test_above_alert_triggers_and_notifies(env):
    alert_id = await _add_alert(env.session_factory, env.user_id)
    env.prices = {"AAPL": 151.0}

    await svc.check_price_alerts()

    alert = await _get_alert(env.session_factory, alert_id)
    assert alert.triggered_at is not None
    assert env.notifications == [("AAPL", "above", 150.0, "price")]
    assert env.analyses == []


@pytest.mark.asyncio
async def test_below_alert_triggers_at_or_under_target(env):
    alert_id = await _add_alert(env.session_factory, env.user_id, condition="below", target_price=Decimal("100"))
    env.prices = {"AAPL": 100.0}

    await svc.check_price_alerts()

    alert = await _get_alert(env.session_factory, alert_id)
    assert alert.triggered_at is not None


@pytest.mark.asyncio
async def test_untouched_when_price_on_safe_side(env):
    alert_id = await _add_alert(env.session_factory, env.user_id)
    env.prices = {"AAPL": 149.99}

    await svc.check_price_alerts()

    alert = await _get_alert(env.session_factory, alert_id)
    assert alert.triggered_at is None
    assert env.notifications == []


@pytest.mark.asyncio
async def test_missing_price_skips_alert(env):
    alert_id = await _add_alert(env.session_factory, env.user_id)
    env.prices = {}

    await svc.check_price_alerts()

    alert = await _get_alert(env.session_factory, alert_id)
    assert alert.triggered_at is None


@pytest.mark.asyncio
async def test_already_triggered_alert_not_rechecked(env):
    await _add_alert(env.session_factory, env.user_id, triggered_at=datetime.now(UTC))
    env.prices = {"AAPL": 200.0}

    await svc.check_price_alerts()
    assert env.notifications == []


@pytest.mark.asyncio
async def test_auto_analyze_schedules_background_analysis(env):
    await _add_alert(env.session_factory, env.user_id, auto_analyze=True)
    env.prices = {"AAPL": 151.0}

    await svc.check_price_alerts()
    # The analysis runs as a fire-and-forget task; yield so it executes.
    await asyncio.sleep(0)

    assert len(env.analyses) == 1
    ticker, trade_date, user_id = env.analyses[0]
    assert ticker == "AAPL"
    assert user_id == env.user_id


@pytest.mark.asyncio
async def test_no_system_settings_still_marks_triggered_without_notification(env):
    alert_id = await _add_alert(env.session_factory, env.user_id)
    env.prices = {"AAPL": 151.0}
    env.sys_settings = None

    await svc.check_price_alerts()

    alert = await _get_alert(env.session_factory, alert_id)
    assert alert.triggered_at is not None
    assert env.notifications == []
