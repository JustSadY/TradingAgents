from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.user import User
from backend.services.signal_backtest_service import get_signal_replay_context


async def test_system_signal_replay_excludes_tenant_history(db: AsyncSession, test_user: User) -> None:
    db.add_all(
        [
            AnalysisResult(
                user_id=None,
                ticker="AAPL",
                trade_date="2026-07-18",
                signal="Buy",
                raw_return=0.05,
                status="completed",
            ),
            AnalysisResult(
                user_id=test_user.id,
                ticker="AAPL",
                trade_date="2026-07-19",
                signal="Sell",
                raw_return=-0.05,
                status="completed",
            ),
        ]
    )
    await db.flush()

    context = await get_signal_replay_context(db, "AAPL", user_id=None)

    assert "Buy: 1 signal(s)" in context
    assert "Sell: 1 signal(s)" not in context
