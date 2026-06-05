from __future__ import annotations

from sqlalchemy import select, desc as _desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.system_settings import SystemSettings
from backend.repositories.common import by_id


async def get_system_settings(db: AsyncSession) -> SystemSettings | None:
    result = await db.execute(select(SystemSettings).where(SystemSettings.id == 1))
    return result.scalar_one_or_none()


async def list_historical_analyses(
    db: AsyncSession,
    *,
    ticker: str,
    before_trade_date: str,
    limit: int,
) -> list[AnalysisResult]:
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.ticker == ticker)
        .where(AnalysisResult.trade_date < before_trade_date)
        .order_by(_desc(AnalysisResult.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_analysis_by_id(db: AsyncSession, analysis_id: int) -> AnalysisResult | None:
    result = await db.execute(by_id(AnalysisResult, analysis_id))
    return result.scalar_one_or_none()
