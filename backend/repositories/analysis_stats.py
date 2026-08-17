from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult


async def list_completed_analyses_for_stats(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    ticker: str | None = None,
    require_raw_return: bool = False,
) -> list[AnalysisResult]:
    query = select(AnalysisResult).where(AnalysisResult.status == "completed")
    if require_raw_return:
        query = query.where(AnalysisResult.raw_return.is_not(None))
    if user_id is not None:
        query = query.where(AnalysisResult.user_id == user_id)
    if ticker:
        query = query.where(AnalysisResult.ticker == ticker.upper())
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_learning_eligible_analyses(
    db: AsyncSession,
    *,
    user_id: int | None,
    asset_type: str | None = None,
) -> list[AnalysisResult]:
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.alpha_return.is_not(None))
        .where(AnalysisResult.learning_eligible.is_(True))
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    if asset_type:
        query = query.where(AnalysisResult.asset_type == asset_type)
    result = await db.execute(query)
    return list(result.scalars().all())
