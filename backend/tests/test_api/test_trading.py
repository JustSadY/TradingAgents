from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestTradingAPI:
    """Tests for the trading API endpoints."""

    async def test_get_portfolio_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/trading/portfolio")
        assert resp.status_code == 401

    async def test_get_portfolio(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        from backend.models.portfolio import Portfolio

        portfolio = Portfolio(
            user_id=test_user.id,
            mode="simulation",
            broker="paper",
            initial_capital=Decimal("100000.0"),
            current_balance=Decimal("100000.0"),
            cash_available=Decimal("100000.0"),
        )
        db.add(portfolio)
        await db.flush()

        resp = await auth_client.get("/api/trading/portfolio")
        assert resp.status_code == 200
        data = resp.json()
        assert "cash_available" in data
        assert "holdings" in data

    async def test_create_order_missing_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/trading/order", json={})
        assert resp.status_code == 422

    async def test_create_order_invalid_ticker(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/trading/order",
            json={"ticker": "", "action": "BUY", "quantity": 10},
        )
        assert resp.status_code == 422

    async def test_create_order_invalid_action(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/trading/order",
            json={"ticker": "AAPL", "action": "INVALID", "quantity": 10},
        )
        assert resp.status_code == 422

    async def test_create_order_negative_quantity(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/trading/order",
            json={"ticker": "AAPL", "action": "BUY", "quantity": -5},
        )
        assert resp.status_code == 422

    async def test_create_order_rejects_unknown_analysis_before_execution(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/trading/order",
            json={"ticker": "AAPL", "action": "BUY", "quantity": 1, "analysis_id": 999999},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Analysis not found"

    async def test_get_performance_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/trading/performance")
        assert resp.status_code == 401

    async def test_get_performance(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/trading/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    async def test_get_portfolio_stats_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/trading/portfolio-stats")
        assert resp.status_code == 401

    async def test_get_portfolio_stats(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        from backend.models.portfolio import Portfolio

        portfolio = Portfolio(
            user_id=test_user.id,
            mode="simulation",
            broker="paper",
            initial_capital=Decimal("100000.0"),
            current_balance=Decimal("100000.0"),
            cash_available=Decimal("100000.0"),
        )
        db.add(portfolio)
        await db.flush()

        resp = await auth_client.get("/api/trading/portfolio-stats")
        assert resp.status_code == 200

    async def test_get_risk_dashboard(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/trading/risk-dashboard")
        assert resp.status_code == 200

    async def test_get_risk_dashboard_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/trading/risk-dashboard")
        assert resp.status_code == 401

    async def test_post_reset_portfolio(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/trading/reset", json={"initial_capital": 50000.0})
        assert resp.status_code == 200
        data = resp.json()
        assert "initial_capital" in data or "cash_balance" in data or "message" in data

    async def test_post_reset_portfolio_no_auth(self, async_client: AsyncClient):
        resp = await async_client.post("/api/trading/reset", json={"initial_capital": 50000.0})
        assert resp.status_code == 401

    async def test_rebalance_portfolio(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/trading/rebalance")
        assert resp.status_code == 200

    async def test_rebalance_portfolio_no_auth(self, async_client: AsyncClient):
        resp = await async_client.post("/api/trading/rebalance")
        assert resp.status_code == 401
