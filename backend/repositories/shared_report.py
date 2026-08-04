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
            AnalysisResult.status == "completed",
        )
    )
    return result.scalar_one_or_none()

async def get_shared_report_by_analysis(
    db: AsyncSession,
    analysis_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> SharedReport | None:
    statement = select(SharedReport).where(
        SharedReport.analysis_id == analysis_id,
        SharedReport.user_id == user_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    return result.scalar_one_or_none()

async def create_shared_report(db: AsyncSession, user_id: int, analysis_id: int) -> SharedReport:
    share = SharedReport(user_id=user_id, analysis_id=analysis_id)
    db.add(share)
    await db.flush()
    return share

async def get_shared_report_by_token(db: AsyncSession, token: str) -> SharedReport | None:
    result = await db.execute(
        select(SharedReport).where(SharedReport.token == token, SharedReport.revoked_at.is_(None))
    )
    return result.scalar_one_or_none()

async def get_analysis_by_id_public(db: AsyncSession, analysis_id: int) -> AnalysisResult | None:
    result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.id == analysis_id,
            AnalysisResult.status == "completed",
        )
    )
    return result.scalar_one_or_none()
