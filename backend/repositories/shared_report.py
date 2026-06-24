from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.shared_report import SharedReport


async def get_user_analysis_by_id(db: AsyncSession, analysis_id: int, user_id: int) -> AnalysisResult | None:
    result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.id == analysis_id,
            AnalysisResult.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_shared_report_by_analysis(
    db: AsyncSession,
    analysis_id: int,
    user_id: int,
    current_time: datetime,
) -> SharedReport | None:
    result = await db.execute(
        select(SharedReport).where(
            SharedReport.analysis_id == analysis_id,
            SharedReport.user_id == user_id,
            SharedReport.expires_at > current_time,
        )
    )
    return result.scalar_one_or_none()


async def create_shared_report(db: AsyncSession, user_id: int, analysis_id: int) -> SharedReport:
    share = SharedReport(user_id=user_id, analysis_id=analysis_id)
    db.add(share)
    await db.flush()
    return share


async def get_shared_report_by_token(db: AsyncSession, token: str) -> SharedReport | None:
    result = await db.execute(select(SharedReport).where(SharedReport.token == token))
    return result.scalar_one_or_none()


async def get_analysis_by_id_public(db: AsyncSession, analysis_id: int) -> AnalysisResult | None:
    result = await db.execute(select(AnalysisResult).where(AnalysisResult.id == analysis_id))
    return result.scalar_one_or_none()
