from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.repositories.token_analytics import get_daily_token_usage_rows, get_token_usage_rows

class TestTokenAnalyticsRepository:
    async def _create_analysis(
        self,
        db: AsyncSession,
        user_id: int,
        tokens_in: int = 100,
        tokens_out: int = 50,
        provider: str = "openai",
        model: str = "gpt-4",
        status: str = "completed",
        days_ago: int = 0,
    ) -> AnalysisResult:
        analysis = AnalysisResult(
            user_id=user_id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status=status,
            llm_provider=provider,
            llm_model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            created_at=datetime.now(UTC),
        )
        db.add(analysis)
        await db.flush()
        return analysis

    async def test_get_token_usage_rows(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=1000, tokens_out=500, provider="openai", model="gpt-4")
        await self._create_analysis(
            db, test_user.id, tokens_in=200, tokens_out=100, provider="anthropic", model="claude-3"
        )

        rows = await get_token_usage_rows(db, test_user.id)
        assert len(rows) == 2

        providers = {r.llm_provider for r in rows}
        assert providers == {"openai", "anthropic"}

    async def test_get_token_usage_rows_aggregates(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=500, tokens_out=250, provider="openai", model="gpt-4")
        await self._create_analysis(db, test_user.id, tokens_in=300, tokens_out=150, provider="openai", model="gpt-4")

        rows = await get_token_usage_rows(db, test_user.id)
        assert len(rows) == 1
        row = rows[0]
        assert row.tokens_in == 800
        assert row.tokens_out == 400
        assert row.analyses == 2

    async def test_get_token_usage_rows_excludes_non_completed(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=500, tokens_out=250, status="running")

        rows = await get_token_usage_rows(db, test_user.id)
        assert len(rows) == 0

    async def test_get_token_usage_rows_scoped(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=100, tokens_out=50)

        other_rows = await get_token_usage_rows(db, 99999)
        assert len(other_rows) == 0

    async def test_get_daily_token_usage_rows(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=100, tokens_out=50)

        rows = await get_daily_token_usage_rows(db, test_user.id)
        assert len(rows) >= 1

    async def test_get_daily_token_usage_rows_limit(self, db: AsyncSession, test_user):
        for i in range(5):
            await self._create_analysis(db, test_user.id, tokens_in=i * 100, tokens_out=i * 50)

        rows = await get_daily_token_usage_rows(db, test_user.id, limit=3)
        assert len(rows) <= 3

    async def test_get_daily_token_usage_rows_excludes_non_completed(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=100, tokens_out=50, status="running")

        rows = await get_daily_token_usage_rows(db, test_user.id)
        assert len(rows) == 0

    async def test_get_daily_token_usage_rows_scoped(self, db: AsyncSession, test_user):
        await self._create_analysis(db, test_user.id, tokens_in=100, tokens_out=50)

        other_rows = await get_daily_token_usage_rows(db, 99999)
        assert len(other_rows) == 0
