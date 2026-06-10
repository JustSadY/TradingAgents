"""Integration tests for the leveraged paper-trading order flow.

Exercises ``execute_order`` and ``get_portfolio_with_live_prices`` against an
in-memory SQLite database with a stubbed price feed, covering margin posting,
borrowing, partial closes, realized P&L, and force-liquidation.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.order import Order  # noqa: F401 — register table
from backend.models.portfolio import Holding, Portfolio  # noqa: F401 — register tables
from backend.services import mock_trading_service as mts


async def _get_holding(db, ticker):
    # A direct SELECT reflects the persisted row (production reads holdings on a
    # fresh session per request; the relationship cache on the fixture's
    # portfolio object would otherwise go stale).
    res = await db.execute(select(Holding).where(Holding.ticker == ticker))
    return res.scalar_one_or_none()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def portfolio(db):
    p = Portfolio(
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("100000"),
        current_balance=Decimal("100000"),
        cash_available=Decimal("100000"),
        margin_used=Decimal("0"),
        status="active",
    )
    db.add(p)
    await db.flush()
    return p


def _set_price(monkeypatch, price):
    async def fake_price(ticker):
        return price

    async def fake_batch(tickers):
        return {t: price for t in tickers}

    monkeypatch.setattr(mts, "get_live_price", fake_price)
    monkeypatch.setattr(mts, "get_live_prices_batch", fake_batch)


async def _lang_noop(db, user):
    return "English"


@pytest.fixture(autouse=True)
def _patch_lang(monkeypatch):
    monkeypatch.setattr(mts, "get_user_language", _lang_noop, raising=False)
    # get_user_language is imported lazily inside execute_order, so patch the source.
    import backend.services.settings_service as settings_service

    monkeypatch.setattr(settings_service, "get_user_language", _lang_noop)


@pytest.mark.asyncio
async def test_leveraged_buy_posts_margin_and_borrows(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    # Buy 100 shares @ $100 = $10,000 notional at 5x leverage.
    res = await mts.execute_order(
        db, "AAPL", "BUY", 100.0, portfolio_id=portfolio.id, leverage=5.0
    )
    assert res["leverage"] == 5.0

    h = await _get_holding(db, "AAPL")
    # margin = 10000/5 = 2000; borrowed = 8000.
    assert h.margin_used == Decimal("2000")
    assert h.borrowed_amount == Decimal("8000")
    # Cash drops by margin + commission (0.1% of 10000 = 10).
    assert portfolio.cash_available == Decimal("100000") - Decimal("2000") - Decimal("10")
    # Maintenance rate for 5x = (1/5)*0.5 = 0.1; liq = 8000/(100*0.9) ≈ 88.89.
    # Crucially this is BELOW the $100 entry, so the position is not immediately
    # liquidatable.
    assert h.liquidation_price > Decimal("88") and h.liquidation_price < Decimal("89")


@pytest.mark.asyncio
async def test_full_close_realizes_pnl_and_repays_loan(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(db, "AAPL", "BUY", 100.0, portfolio_id=portfolio.id, leverage=5.0)
    cash_after_buy = portfolio.cash_available

    # Price rises to $120; close the whole position.
    _set_price(monkeypatch, 120.0)
    res = await mts.execute_order(db, "AAPL", "SELL", 100.0, portfolio_id=portfolio.id)

    # Gross gain = (120-100)*100 = 2000; minus commission (0.1% of 12000 = 12).
    assert abs(res["realized_pnl"] - (2000.0 - 12.0)) < 0.01
    # Cash back = proceeds(12000) - repaid borrowed(8000) - commission(12).
    assert abs(float(portfolio.cash_available - cash_after_buy) - (12000 - 8000 - 12)) < 0.01
    # Position fully closed.
    assert await _get_holding(db, "AAPL") is None
    assert portfolio.margin_used == Decimal("0")


@pytest.mark.asyncio
async def test_liquidation_when_price_crashes(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(db, "AAPL", "BUY", 100.0, portfolio_id=portfolio.id, leverage=5.0)

    # Crash below the ~88.89 liquidation price.
    _set_price(monkeypatch, 85.0)
    db.expunge_all()
    data = await mts.get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)

    assert len(data["liquidations"]) == 1
    assert data["liquidations"][0]["ticker"] == "AAPL"
    assert len(data["holdings"]) == 0
    # A LIQUIDATED order was recorded.
    orders = (await db.execute(Order.__table__.select().where(Order.status == "LIQUIDATED"))).all()
    assert len(orders) == 1


@pytest.mark.asyncio
async def test_spot_buy_never_liquidates(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(db, "AAPL", "BUY", 50.0, portfolio_id=portfolio.id, leverage=1.0)

    # Even a deep drop cannot liquidate a cash (1x) position.
    _set_price(monkeypatch, 1.0)
    db.expunge_all()
    data = await mts.get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)
    assert data["liquidations"] == []
    assert len(data["holdings"]) == 1
    assert data["holdings"][0]["leverage"] == 1.0


@pytest.mark.asyncio
async def test_leverage_clamped_to_max(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    res = await mts.execute_order(db, "AAPL", "BUY", 10.0, portfolio_id=portfolio.id, leverage=999.0)
    assert res["leverage"] == 10.0  # capped


@pytest.mark.asyncio
async def test_stop_loss_auto_closes(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(
        db, "AAPL", "BUY", 10.0, portfolio_id=portfolio.id, stop_loss=90.0, take_profit=130.0
    )
    h = await _get_holding(db, "AAPL")
    assert float(h.stop_loss) == 90.0 and float(h.take_profit) == 130.0

    # Drop to the stop level → auto-close with reason STOP_LOSS.
    _set_price(monkeypatch, 89.0)
    db.expunge_all()
    data = await mts.get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)
    assert any(c["reason"] == "STOP_LOSS" for c in data["auto_closes"])
    assert len(data["holdings"]) == 0


@pytest.mark.asyncio
async def test_take_profit_auto_closes(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(
        db, "AAPL", "BUY", 10.0, portfolio_id=portfolio.id, stop_loss=90.0, take_profit=130.0
    )
    # Rally past the target → auto-close with reason TAKE_PROFIT.
    _set_price(monkeypatch, 131.0)
    db.expunge_all()
    data = await mts.get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)
    assert any(c["reason"] == "TAKE_PROFIT" for c in data["auto_closes"])
    assert len(data["holdings"]) == 0


@pytest.mark.asyncio
async def test_monitor_open_positions_sweeps(db, portfolio, monkeypatch):
    _set_price(monkeypatch, 100.0)
    await mts.execute_order(db, "AAPL", "BUY", 10.0, portfolio_id=portfolio.id, stop_loss=95.0)
    _set_price(monkeypatch, 94.0)
    db.expunge_all()
    closed = await mts.monitor_open_positions(db)
    assert any(c["reason"] == "STOP_LOSS" and c["ticker"] == "AAPL" for c in closed)
