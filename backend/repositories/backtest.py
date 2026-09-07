from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.models.analysis import AnalysisResult

_CONSENSUS_BACKTEST_COLUMNS = (
    AnalysisResult.id,
    AnalysisResult.trade_date,
    AnalysisResult.created_at,
    AnalysisResult.signal,
    AnalysisResult.portfolio_decision_json,
    AnalysisResult.chart_annotations,
)


async def list_consensus_analyses(
    db: AsyncSession,
    *,
    user_id: int,
    ticker: str,
    start_date: str,
    end_date: str,
) -> list[AnalysisResult]:
    """Return completed consensus-analysis candidates in deterministic order.

    Causal timestamp validation intentionally stays in ``backtest_service``;
    this repository only owns persistence selection and ordering. The simulator
    consumes only the accepted signal/allocation, chart exits, trade date and
    causal creation timestamp, so detail reports stay off this bulk query.
    """
    query = (
        select(AnalysisResult)
        .where(
            AnalysisResult.ticker == ticker.upper(),
            AnalysisResult.trade_date >= start_date,
            AnalysisResult.trade_date <= end_date,
            AnalysisResult.user_id == user_id,
            AnalysisResult.status == "completed",
        )
        .options(load_only(*_CONSENSUS_BACKTEST_COLUMNS))
        .order_by(AnalysisResult.trade_date.asc(), AnalysisResult.created_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())
