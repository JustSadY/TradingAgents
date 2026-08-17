from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.repositories.performance import list_resolved_learning_analyses


async def test_resolved_performance_history_keeps_system_scope_isolated(
    db: AsyncSession,
    test_user: User,
) -> None:
    system_row = AnalysisResult(
        user_id=None,
        ticker="AAPL",
        trade_date="2026-07-01",
        asset_type="stock",
        status="completed",
        learning_eligible=True,
        raw_return=0.05,
    )
    tenant_row = AnalysisResult(
        user_id=test_user.id,
        ticker="AAPL",
        trade_date="2026-07-02",
        asset_type="stock",
        status="completed",
        learning_eligible=True,
        raw_return=-0.03,
    )
    db.add_all([system_row, tenant_row])
    await db.flush()

    system_rows = await list_resolved_learning_analyses(db, user_id=None)
    tenant_rows = await list_resolved_learning_analyses(db, user_id=test_user.id)

    assert [row.id for row in system_rows] == [system_row.id]
    assert [row.id for row in tenant_rows] == [tenant_row.id]
