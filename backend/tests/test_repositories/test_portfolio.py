from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.models.user import User
from backend.repositories.portfolio import (
    get_active_holdings_by_portfolio_id,
    get_holding,
    get_order_by_id,
    get_portfolio_by_id,
    get_simulation_portfolio,
    list_holdings,
    list_orders,
    list_portfolios,
)

class TestPortfolioRepository:
    async def _create_portfolio(self, db: AsyncSession, user_id: int, mode: str = "simulation") -> Portfolio:
        portfolio = Portfolio(
            user_id=user_id,
            mode=mode,
            broker="test_broker",
            initial_capital=Decimal("100000.00"),
            current_balance=Decimal("100000.00"),
            cash_available=Decimal("100000.00"),
        )
        db.add(portfolio)
        await db.flush()
        return portfolio

    async def _create_holding(self, db: AsyncSession, portfolio_id: int, ticker: str = "AAPL") -> Holding:
        holding = Holding(
            portfolio_id=portfolio_id,
            ticker=ticker,
            quantity=Decimal("10.0"),
            avg_buy_price=Decimal("150.00"),
            current_price=Decimal("155.00"),
            unrealized_pnl=Decimal("50.00"),
        )
        db.add(holding)
        await db.flush()
        return holding

    async def _create_order(
        self, db: AsyncSession, portfolio_id: int, ticker: str = "AAPL", action: str = "BUY"
    ) -> Order:
        order = Order(
            portfolio_id=portfolio_id,
            broker="test_broker",
            ticker=ticker,
            action=action,
            quantity_requested=Decimal("10.0"),
            quantity_filled=Decimal("10.0"),
            status="FILLED",
            price_per_share=Decimal("150.00"),
            total_value=Decimal("1500.00"),
        )
        db.add(order)
        await db.flush()
        return order

    async def test_create_portfolio(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        assert portfolio.id is not None
        assert portfolio.mode == "simulation"
        assert portfolio.current_balance == Decimal("100000.00")

    async def test_get_portfolio_by_id(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        found = await get_portfolio_by_id(db, portfolio.id, user=test_user)
        assert found is not None
        assert found.id == portfolio.id

    async def test_get_portfolio_by_id_scoped(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        found = await get_portfolio_by_id(db, portfolio.id, user=other_user)
        assert found is None

    async def test_get_simulation_portfolio(self, db: AsyncSession, test_user: User):
        await self._create_portfolio(db, test_user.id)
        found = await get_simulation_portfolio(db, user_id=test_user.id)
        assert found is not None
        assert found.mode == "simulation"

    async def test_get_holding(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        holding = await self._create_holding(db, portfolio.id)
        found = await get_holding(db, portfolio.id, "AAPL")
        assert found is not None
        assert found.id == holding.id

    async def test_list_portfolios(self, db: AsyncSession, test_user: User):
        await self._create_portfolio(db, test_user.id, mode="simulation")
        await self._create_portfolio(db, test_user.id, mode="live")

        portfolios = await list_portfolios(db, user=test_user)
        assert len(portfolios) == 2

    async def test_list_portfolios_scoped(self, db: AsyncSession, test_user: User, admin_user: User):
        await self._create_portfolio(db, test_user.id)
        await self._create_portfolio(db, admin_user.id)

        user_portfolios = await list_portfolios(db, user=test_user)
        assert len(user_portfolios) == 1

        admin_portfolios = await list_portfolios(db, user=admin_user)
        assert len(admin_portfolios) == 2

    async def test_list_holdings(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        await self._create_holding(db, portfolio.id, "AAPL")
        await self._create_holding(db, portfolio.id, "GOOGL")

        holdings = await list_holdings(db, user=test_user)
        assert len(holdings) == 2

    async def test_get_active_holdings(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        h1 = await self._create_holding(db, portfolio.id, "AAPL")
        h2 = await self._create_holding(db, portfolio.id, "GOOGL")
        h2.quantity = Decimal("0")
        await db.flush()

        active = await get_active_holdings_by_portfolio_id(db, portfolio.id)
        assert len(active) == 1
        assert active[0].id == h1.id

    async def test_list_orders(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        await self._create_order(db, portfolio.id, "AAPL", "BUY")
        await self._create_order(db, portfolio.id, "GOOGL", "SELL")

        orders = await list_orders(db, user=test_user)
        assert len(orders) == 2

    async def test_get_order_by_id(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        order = await self._create_order(db, portfolio.id)
        found = await get_order_by_id(db, order.id, user=test_user)
        assert found is not None
        assert found.id == order.id

    async def test_get_order_by_id_scoped(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        order = await self._create_order(db, portfolio.id)
        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        found = await get_order_by_id(db, order.id, user=other_user)
        assert found is None

    async def test_list_orders_filter_by_ticker(self, db: AsyncSession, test_user: User):
        portfolio = await self._create_portfolio(db, test_user.id)
        await self._create_order(db, portfolio.id, "AAPL", "BUY")
        await self._create_order(db, portfolio.id, "GOOGL", "BUY")

        orders = await list_orders(db, user=test_user, ticker="AAPL")
        assert len(orders) == 1
