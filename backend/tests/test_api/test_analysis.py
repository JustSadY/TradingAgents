from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.schemas.analysis import AnalysisListItem


@pytest.mark.parametrize(
    ("legacy_signal", "expected"),
    [
        ("buy", "Buy"),
        ("  SELL  ", "Sell"),
        ("unexpected", None),
    ],
)
def test_analysis_list_signal_normalizes_legacy_values(legacy_signal: str, expected: str | None):
    item = AnalysisListItem.model_validate(
        {
            "id": 1,
            "ticker": "AAPL",
            "trade_date": "2026-07-18",
            "asset_type": "stock",
            "signal": legacy_signal,
            "duration_seconds": 1.0,
            "triggered_by": "manual",
            "created_at": datetime.now(UTC),
        }
    )

    assert item.signal == expected


class TestAnalysisAPI:
    """Tests for the analysis API endpoints."""

    async def test_get_latest_analysis_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/analysis/latest")
        assert resp.status_code == 401

    async def test_get_latest_analysis_empty(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/analysis/latest")
        assert resp.status_code == 404

    async def test_get_latest_analysis_with_data(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
            market_report="Test report",
        )
        db.add(analysis)
        await db.flush()

        resp = await auth_client.get("/api/analysis/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["signal"] == "Buy"
        assert data["market_report"] == "Test report"

    async def test_get_latest_analysis_scoped(
        self, async_client: AsyncClient, auth_client: AsyncClient, db: AsyncSession, test_user
    ):
        # Create analysis for this user
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        resp = await auth_client.get("/api/analysis/latest")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "AAPL"

    async def test_list_analysis_history(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        for ticker in ["AAPL", "GOOGL", "MSFT"]:
            db.add(
                AnalysisResult(
                    user_id=test_user.id,
                    ticker=ticker,
                    trade_date="2026-07-18",
                    signal="buy",
                    status="completed",
                    market_report="Test",
                )
            )
        await db.flush()

        resp = await auth_client.get("/api/analysis/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_list_analysis_history_filter_ticker(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        for ticker in ["AAPL", "GOOGL"]:
            db.add(
                AnalysisResult(
                    user_id=test_user.id,
                    ticker=ticker,
                    trade_date="2026-07-18",
                    signal="buy",
                    status="completed",
                )
            )
        await db.flush()

        resp = await auth_client.get("/api/analysis/history?ticker=AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["signal"] == "Buy"

    async def test_list_analysis_history_limit(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        for i in range(10):
            db.add(
                AnalysisResult(
                    user_id=test_user.id,
                    ticker=f"TICK{i}",
                    trade_date="2026-07-18",
                    signal="buy",
                    status="completed",
                )
            )
        await db.flush()

        resp = await auth_client.get("/api/analysis/history?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_get_analysis_by_id(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
            market_report="Detailed analysis",
        )
        db.add(analysis)
        await db.flush()

        resp = await auth_client.get(f"/api/analysis/{analysis.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["market_report"] == "Detailed analysis"

    async def test_get_analysis_by_id_not_found(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/analysis/99999")
        assert resp.status_code == 404

    async def test_get_analysis_by_id_scoped(
        self, auth_client: AsyncClient, async_client: AsyncClient, db: AsyncSession, test_user
    ):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        # This user owns the analysis - should work
        resp = await auth_client.get(f"/api/analysis/{analysis.id}")
        assert resp.status_code == 200

    async def test_get_analysis_chat_empty(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        resp = await auth_client.get(f"/api/analysis/{analysis.id}/chat")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_cost_estimate(self, auth_client: AsyncClient, db: AsyncSession, test_user):
        from backend.models.settings import AppSettings

        settings = AppSettings(user_id=test_user.id)
        db.add(settings)
        await db.flush()

        resp = await auth_client.get("/api/analysis/cost-estimate")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) >= {
            "analyst_count",
            "estimated_tokens",
            "estimated_cost_usd",
            "estimated_duration_min",
            "pricing_source",
            "pricing_is_fallback",
        }
        assert data["analyst_count"] > 0
        assert data["estimated_tokens"] > 0
        assert data["estimated_cost_usd"] >= 0
        assert isinstance(data["pricing_source"], str)
        assert isinstance(data["pricing_is_fallback"], bool)

    async def test_get_analysis_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/analysis/history")
        assert resp.status_code == 401

    async def test_get_active_tasks_empty(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/analysis/active")
        assert resp.status_code == 200
        assert resp.json() == []
