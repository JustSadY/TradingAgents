from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.models.user import User


def _make_portfolio(user_id: int, **overrides) -> Portfolio:
    defaults = {
        "user_id": user_id,
        "mode": "simulation",
        "broker": "simulation",
        "initial_capital": Decimal("100000.0"),
        "current_balance": Decimal("100000.0"),
        "cash_available": Decimal("80000.0"),
    }
    defaults.update(overrides)
    return Portfolio(**defaults)


class TestPortfolioAPI:
    """Tests for the portfolio API endpoints."""

    async def test_list_portfolios_empty(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        resp = await auth_client.get("/api/portfolio")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_portfolios(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        portfolio = _make_portfolio(test_user.id)
        db.add(portfolio)
        await db.flush()

        resp = await auth_client.get("/api/portfolio")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["mode"] == "simulation"

    async def test_list_holdings_empty(
        self, auth_client: AsyncClient
    ):
        resp = await auth_client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_holdings(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        portfolio = _make_portfolio(test_user.id)
        db.add(portfolio)
        await db.flush()

        holding = Holding(
            portfolio_id=portfolio.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            avg_buy_price=Decimal("150.0"),
        )
        db.add(holding)
        await db.flush()

        resp = await auth_client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    async def test_list_holdings_scoped(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        other_user = User(username="otheruser", hashed_password=hash_password("pw"), is_active=True, role="user")
        db.add(other_user)
        await db.flush()

        other_portfolio = _make_portfolio(other_user.id)
        db.add(other_portfolio)
        await db.flush()

        db.add(Holding(
            portfolio_id=other_portfolio.id,
            ticker="GOOGL",
            quantity=Decimal("5"),
            avg_buy_price=Decimal("200.0"),
        ))
        await db.flush()

        resp = await auth_client.get("/api/portfolio/holdings")
        assert resp.status_code == 200
        data = resp.json()

        tickers = [h["ticker"] for h in data]
        assert "GOOGL" not in tickers

    async def test_list_orders_empty(
        self, auth_client: AsyncClient
    ):
        resp = await auth_client.get("/api/portfolio/orders")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_orders(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        portfolio = _make_portfolio(test_user.id)
        db.add(portfolio)
        await db.flush()

        order = Order(
            portfolio_id=portfolio.id,
            broker="simulation",
            ticker="AAPL",
            action="BUY",
            quantity_requested=Decimal("10"),
            quantity_filled=Decimal("10"),
            status="FILLED",
            price_per_share=Decimal("150.0"),
            total_value=Decimal("1500.0"),
        )
        db.add(order)
        await db.flush()

        resp = await auth_client.get("/api/portfolio/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    async def test_list_orders_filter_ticker(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        portfolio = _make_portfolio(test_user.id)
        db.add(portfolio)
        await db.flush()

        db.add(Order(portfolio_id=portfolio.id, broker="simulation", ticker="AAPL", action="BUY",
                      quantity_requested=Decimal("10"), quantity_filled=Decimal("10"),
                      status="FILLED", price_per_share=Decimal("150.0"), total_value=Decimal("1500.0")))
        db.add(Order(portfolio_id=portfolio.id, broker="simulation", ticker="GOOGL", action="BUY",
                      quantity_requested=Decimal("5"), quantity_filled=Decimal("5"),
                      status="FILLED", price_per_share=Decimal("200.0"), total_value=Decimal("1000.0")))
        await db.flush()

        resp = await auth_client.get("/api/portfolio/orders?ticker=AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"

    async def test_list_orders_limit(
        self, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        portfolio = _make_portfolio(test_user.id)
        db.add(portfolio)
        await db.flush()

        for i in range(5):
            db.add(Order(
                portfolio_id=portfolio.id, broker="simulation", ticker=f"TICK{i}", action="BUY",
                quantity_requested=Decimal("1"), quantity_filled=Decimal("1"),
                status="FILLED", price_per_share=Decimal("100.0"), total_value=Decimal("100.0"),
            ))
        await db.flush()

        resp = await auth_client.get("/api/portfolio/orders?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_list_portfolios_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/portfolio")
        assert resp.status_code == 401

    async def test_list_holdings_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/portfolio/holdings")
        assert resp.status_code == 401

    async def test_list_orders_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/portfolio/orders")
        assert resp.status_code == 401
