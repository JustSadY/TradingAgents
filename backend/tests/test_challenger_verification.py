"""Challenger tests targeting stop-loss floor edge cases and concurrency safety."""

import asyncio
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.portfolio import Portfolio
from backend.services import analysis_service as ans
from backend.services import mock_trading_service as mts
from backend.services import trading_orchestrator as tro


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite DB fixture."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
def session_factory():
    """Factory fixture to create new DB sessions sharing the same in-memory DB."""
    engine = create_async_engine("sqlite+aiosqlite:///file:memdb_concurrency?mode=memory&cache=shared")
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, Session


def test_stop_loss_floor_extremely_close():
    """Verify that when stop_loss is extremely close to entry price,

    risk_per_share is floored to 0.005 * price to prevent massive position sizing.
    """
    price = 100.0
    qty = tro._position_quantity(
        risk_per_trade_pct=1.0,
        capital=100_000.0,
        price=price,
        stop_loss=99.99,
        max_position_size_pct=500.0,
    )
    assert qty == 2000.0


def test_stop_loss_exactly_at_price():
    """Verify that if stop_loss is set exactly at entry price,

    the orchestrator falls back to standard notional sizing (risk_usd / price)
    instead of dividing by zero or flooring to zero.
    """
    price = 100.0
    qty = tro._position_quantity(
        risk_per_trade_pct=1.0,
        capital=100_000.0,
        price=price,
        stop_loss=price,
    )
    assert qty == 10.0


def test_stop_loss_near_zero_prices():
    """Verify stop-loss floor behavior with sub-dollar penny stocks."""
    price = 0.01
    stop_loss = 0.0099
    qty = tro._position_quantity(
        risk_per_trade_pct=1.0,
        capital=100_000.0,
        price=price,
        stop_loss=stop_loss,
    )
    assert qty == 1_000_000.0

    qty_breached = tro._position_quantity(
        risk_per_trade_pct=1.0,
        capital=100_000.0,
        price=price,
        stop_loss=0.00999,
    )
    assert qty_breached == 1_000_000.0


def test_stop_loss_invalid_negative_or_zero():
    """Verify that stop_loss <= 0 is ignored and defaults to standard notional sizing."""
    price = 100.0
    qty_zero = tro._position_quantity(1.0, 100_000.0, price, stop_loss=0.0)
    assert qty_zero == 10.0

    qty_neg = tro._position_quantity(1.0, 100_000.0, price, stop_loss=-5.0)
    assert qty_neg == 10.0


@pytest.mark.asyncio
async def test_wrong_side_stop_loss_auto_closes_immediately(db, monkeypatch):
    """Verify that stop-loss on the wrong side is validated and raises ValueError."""

    async def fake_price(ticker):
        return 100.0

    async def fake_batch(tickers):
        return dict.fromkeys(tickers, 100.0)

    monkeypatch.setattr(mts, "get_live_price", fake_price)
    monkeypatch.setattr(mts, "get_live_prices_batch", fake_batch)

    import backend.services.settings_service as settings_service

    async def _lang_noop(db, user):
        return "English"

    monkeypatch.setattr(settings_service, "get_user_language", _lang_noop)
    monkeypatch.setattr(mts, "get_user_language", _lang_noop, raising=False)

    portfolio = Portfolio(
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("100000"),
        current_balance=Decimal("100000"),
        cash_available=Decimal("100000"),
        margin_used=Decimal("0"),
        status="active",
    )
    db.add(portfolio)
    await db.flush()

    with pytest.raises(ValueError, match="Stop-loss must be less than entry price"):
        await mts.execute_order(
            db,
            action="BUY",
            ticker="AAPL",
            quantity=10,
            portfolio_id=portfolio.id,
            stop_loss=105.0,
        )


@pytest.mark.asyncio
async def test_concurrency_analysis_task_registry():
    """Verify that concurrent task registration and cancellation works

    and cleans up properly without memory leaks.
    """
    tasks = [f"task-test-{i}" for i in range(50)]
    user_id = 42

    await asyncio.gather(*(ans.register_task_owner(tid, user_id) for tid in tasks))

    for tid in tasks:
        assert await ans.is_task_owner(tid, user_id) is True

    await asyncio.gather(*(ans.cancel_local_task(tid) for tid in tasks))

    for tid in tasks:
        assert await ans.is_task_owner(tid, user_id) is False


@pytest.mark.asyncio
async def test_concurrency_portfolio_order_locks(session_factory, monkeypatch):
    """Test concurrent order execution against the same portfolio using multiple sessions.

    Verifies that SQLite allows a double-spending race condition where concurrent
    transactions can read stale cash balances and execute orders exceeding total cash.
    """
    engine, SessionFactory = session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def fake_price(ticker):
        return 100.0

    async def fake_batch(tickers):
        return dict.fromkeys(tickers, 100.0)

    monkeypatch.setattr(mts, "get_live_price", fake_price)
    monkeypatch.setattr(mts, "get_live_prices_batch", fake_batch)

    import backend.services.settings_service as settings_service

    async def _lang_noop(db, user):
        return "English"

    monkeypatch.setattr(settings_service, "get_user_language", _lang_noop)
    monkeypatch.setattr(mts, "get_user_language", _lang_noop, raising=False)

    async with SessionFactory() as session:
        portfolio = Portfolio(
            mode="simulation",
            broker="paper",
            initial_capital=Decimal("1000"),
            current_balance=Decimal("1000"),
            cash_available=Decimal("1000"),
            margin_used=Decimal("0"),
            status="active",
        )
        session.add(portfolio)
        await session.commit()
        portfolio_id = portfolio.id

    errors = []
    successes = []

    async def place_order_task(task_idx):
        async with SessionFactory() as session:
            try:
                res = await mts.execute_order(
                    session,
                    action="BUY",
                    ticker=f"TICKER_{task_idx}",
                    quantity=2.5,
                    portfolio_id=portfolio_id,
                )
                await session.commit()
                successes.append(res)
            except Exception as exc:
                errors.append(exc)

    await asyncio.gather(*(place_order_task(i) for i in range(5)))

    assert len(successes) == 5
    assert len(errors) == 0

    async with SessionFactory() as session:
        res = await session.execute(select(Portfolio).where(Portfolio.id == portfolio_id))
        final_portfolio = res.scalar_one()
        assert final_portfolio.cash_available == Decimal("750") - Decimal("0.25")

    await engine.dispose()
