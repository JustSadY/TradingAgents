from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.repositories.shared_report import (
    create_shared_report,
    get_analysis_by_id_public,
    get_shared_report_by_analysis,
    get_shared_report_by_token,
    get_user_analysis_by_id,
)


class TestSharedReportRepository:
    async def test_create_shared_report(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        share = await create_shared_report(db, user_id=test_user.id, analysis_id=analysis.id)
        assert share.id is not None
        assert share.analysis_id == analysis.id
        assert share.user_id == test_user.id
        assert share.token is not None

    async def test_get_shared_report_by_analysis(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        share = await create_shared_report(db, user_id=test_user.id, analysis_id=analysis.id)

        found = await get_shared_report_by_analysis(db, analysis.id, test_user.id)
        assert found is not None
        assert found.id == share.id

    async def test_get_shared_report_by_analysis_returns_expired_rows(self, db: AsyncSession, test_user):
        """Expiry is deliberately *not* filtered here.

        ``share_service`` needs the existing row even once it has expired so it
        can rotate the token in place rather than violating the
        ``uq_shared_reports_user_analysis`` constraint with a second insert.
        Active/expired is decided there, not in the repository.
        """
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        share = await create_shared_report(db, user_id=test_user.id, analysis_id=analysis.id)
        share.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db.flush()

        found = await get_shared_report_by_analysis(db, analysis.id, test_user.id)
        assert found is not None
        assert found.id == share.id

    async def test_get_shared_report_by_analysis_is_scoped_to_owner(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        await create_shared_report(db, user_id=test_user.id, analysis_id=analysis.id)

        assert await get_shared_report_by_analysis(db, analysis.id, test_user.id + 1) is None

    async def test_get_shared_report_by_token(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        share = await create_shared_report(db, user_id=test_user.id, analysis_id=analysis.id)

        found = await get_shared_report_by_token(db, share.token)
        assert found is not None
        assert found.id == share.id

    async def test_get_shared_report_by_token_invalid(self, db: AsyncSession):
        found = await get_shared_report_by_token(db, "invalid-token")
        assert found is None

    async def test_get_user_analysis_by_id(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        found = await get_user_analysis_by_id(db, analysis.id, test_user.id)
        assert found is not None
        assert found.id == analysis.id

    async def test_get_user_analysis_by_id_scoped(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        found = await get_user_analysis_by_id(db, analysis.id, 99999)
        assert found is None

    async def test_get_analysis_by_id_public(self, db: AsyncSession, test_user):
        analysis = AnalysisResult(
            user_id=test_user.id,
            ticker="AAPL",
            trade_date="2026-07-18",
            signal="buy",
            status="completed",
        )
        db.add(analysis)
        await db.flush()

        found = await get_analysis_by_id_public(db, analysis.id)
        assert found is not None
        assert found.ticker == "AAPL"

    async def test_get_analysis_by_id_public_nonexistent(self, db: AsyncSession):
        found = await get_analysis_by_id_public(db, 999)
        assert found is None
