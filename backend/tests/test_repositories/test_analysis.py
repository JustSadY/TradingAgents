from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.repositories.analysis import (
    cleanup_stale_analyses,
    create_analysis_result,
    get_analysis_by_id,
    get_latest_analysis,
    get_previous_signal,
    get_sentiment_history_by_ticker,
    list_analyses,
    list_historical_analyses,
    update_analysis_result,
)


class TestAnalysisRepository:
    async def _create_analysis(
        self, db: AsyncSession, user_id: int, ticker: str = "AAPL", status: str = "completed", **overrides
    ) -> AnalysisResult:
        kwargs = {
            "user_id": user_id,
            "ticker": ticker,
            "trade_date": "2026-07-18",
            "signal": "buy",
            "status": status,
            "market_report": "test report",
        }
        kwargs.update(overrides)
        return await create_analysis_result(db, **kwargs)

    async def test_create_analysis_result(self, db: AsyncSession, test_user: User):
        analysis = await self._create_analysis(db, test_user.id)
        assert analysis.id is not None
        assert analysis.ticker == "AAPL"
        assert analysis.status == "completed"
        assert analysis.user_id == test_user.id

    async def test_get_analysis_by_id(self, db: AsyncSession, test_user: User):
        analysis = await self._create_analysis(db, test_user.id)
        found = await get_analysis_by_id(db, analysis.id, user=test_user)
        assert found is not None
        assert found.id == analysis.id

    async def test_get_analysis_by_id_scoped(self, db: AsyncSession, test_user: User, admin_user: User):
        analysis = await self._create_analysis(db, test_user.id)

        found = await get_analysis_by_id(db, analysis.id, user=test_user)
        assert found is not None

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        not_found = await get_analysis_by_id(db, analysis.id, user=other_user)
        assert not_found is None

    async def test_get_analysis_by_id_admin_sees_all(self, db: AsyncSession, test_user: User, admin_user: User):
        analysis = await self._create_analysis(db, test_user.id)
        found = await get_analysis_by_id(db, analysis.id, user=admin_user)
        assert found is not None

    async def test_list_analyses(self, db: AsyncSession, test_user: User):
        for ticker in ["AAPL", "GOOGL", "MSFT"]:
            await self._create_analysis(db, test_user.id, ticker=ticker)
        results = await list_analyses(db, user=test_user)
        assert len(results) == 3

    async def test_list_analyses_scoped(self, db: AsyncSession, test_user: User, admin_user: User):
        await self._create_analysis(db, test_user.id, ticker="AAPL")
        await self._create_analysis(db, admin_user.id, ticker="GOOGL")

        user_results = await list_analyses(db, user=test_user)
        assert len(user_results) == 1
        assert user_results[0].ticker == "AAPL"

        admin_results = await list_analyses(db, user=admin_user)
        # Administrators deliberately have cross-user visibility; ordinary
        # users above remain scoped to their own records.
        assert {result.ticker for result in admin_results} == {"AAPL", "GOOGL"}

    async def test_list_analyses_filter_by_ticker(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, ticker="AAPL")
        await self._create_analysis(db, test_user.id, ticker="GOOGL")
        results = await list_analyses(db, user=test_user, ticker="AAPL")
        assert len(results) == 1

    async def test_list_analyses_excludes_non_completed(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, status="running")
        results = await list_analyses(db, user=test_user)
        assert len(results) == 0

    async def test_list_historical_analyses(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, trade_date="2026-07-17")
        await self._create_analysis(db, test_user.id, trade_date="2026-07-18")

        results = await list_historical_analyses(db, ticker="AAPL", before_trade_date="2026-07-18", limit=10)
        assert len(results) == 1

    async def test_get_previous_signal(self, db: AsyncSession, test_user: User):
        a1 = await self._create_analysis(db, test_user.id, signal="buy")
        a2 = await self._create_analysis(db, test_user.id, signal="sell")

        prev = await get_previous_signal(db, user_id=test_user.id, ticker="AAPL", exclude_id=a2.id)
        assert prev == "buy"

        prev = await get_previous_signal(db, user_id=test_user.id, ticker="AAPL", exclude_id=a1.id)
        assert prev is None

    async def test_get_latest_analysis(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, ticker="AAPL")
        await self._create_analysis(db, test_user.id, ticker="GOOGL")

        latest = await get_latest_analysis(db, user=test_user)
        assert latest is not None
        assert latest.ticker == "GOOGL"

    async def test_get_sentiment_history(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, ticker="AAPL", trade_date="2026-07-17")
        await self._create_analysis(db, test_user.id, ticker="AAPL", trade_date="2026-07-18")

        history = await get_sentiment_history_by_ticker(db, "AAPL", user=test_user)
        assert len(history) == 2

    async def test_update_analysis_result(self, db: AsyncSession, test_user: User):
        analysis = await self._create_analysis(db, test_user.id, signal="buy")
        updated = await update_analysis_result(db, analysis.id, signal="sell", market_report="updated report")
        assert updated is not None
        assert updated.signal == "sell"
        assert updated.market_report == "updated report"

    async def test_update_analysis_result_rolls_back_when_commit_is_cancelled(self):
        """A cancelled asyncpg flush must not poison the caller's session."""

        row = SimpleNamespace(signal="buy")

        class _Result:
            def scalar_one_or_none(self):
                return row

        class _Session:
            def __init__(self):
                self.calls: list[str] = []

            async def execute(self, _statement):
                self.calls.append("execute")
                return _Result()

            async def commit(self):
                self.calls.append("commit")
                raise asyncio.CancelledError

            async def rollback(self):
                self.calls.append("rollback")

        session = _Session()

        with pytest.raises(asyncio.CancelledError):
            await update_analysis_result(session, 17, signal="sell")

        assert row.signal == "sell"
        assert session.calls == ["execute", "commit", "rollback"]

    async def test_update_analysis_result_keeps_cancellation_when_rollback_fails(self):
        """Rollback cleanup must not convert a Stop request into a DB failure."""

        class _Result:
            def scalar_one_or_none(self):
                return SimpleNamespace(signal="buy")

        class _Session:
            async def execute(self, _statement):
                return _Result()

            async def commit(self):
                raise asyncio.CancelledError

            async def rollback(self):
                raise RuntimeError("connection dropped during rollback")

        with pytest.raises(asyncio.CancelledError):
            await update_analysis_result(_Session(), 17, signal="sell")

    async def test_cleanup_stale_analyses(self, db: AsyncSession, test_user: User):
        await self._create_analysis(db, test_user.id, status="running")
        await self._create_analysis(db, test_user.id, status="completed")

        count = await cleanup_stale_analyses(db)
        assert count == 1

        remaining = await list_analyses(db, user=test_user)
        assert len(remaining) == 1

    async def test_create_analysis_with_task_id(self, db: AsyncSession, test_user: User):
        analysis = await create_analysis_result(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            task_id="test-task-123",
        )
        assert analysis.task_id == "test-task-123"

        same = await create_analysis_result(
            db,
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            task_id="test-task-123",
            signal="buy",
        )
        assert same.id == analysis.id
        assert same.signal == "buy"
