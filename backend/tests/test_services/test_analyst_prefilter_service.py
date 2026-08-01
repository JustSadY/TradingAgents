from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.services import analyst_prefilter_service

async def test_system_prefilter_excludes_tenant_history(db: AsyncSession, test_user: User, monkeypatch) -> None:
    system_row = AnalysisResult(
        user_id=None,
        ticker="AAPL",
        trade_date="2026-07-18",
        signal="Buy",
        raw_return=0.05,
        status="completed",
    )
    tenant_row = AnalysisResult(
        user_id=test_user.id,
        ticker="AAPL",
        trade_date="2026-07-19",
        signal="Sell",
        raw_return=-0.05,
        status="completed",
    )
    db.add_all([system_row, tenant_row])
    await db.flush()

    captured: list[AnalysisResult] = []

    def capture_rows(rows, _report_fields):
        captured.extend(rows)
        return {}

    monkeypatch.setattr(analyst_prefilter_service, "grade_analyst_winrates", capture_rows)

    kept, dropped = await analyst_prefilter_service.filter_analysts_by_history(
        db,
        "AAPL",
        user_id=None,
        permitted=["market"],
    )

    assert kept == ["market"]
    assert dropped == []
    assert [row.id for row in captured] == [system_row.id]
