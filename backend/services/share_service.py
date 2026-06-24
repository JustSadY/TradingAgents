from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.shared_report import SharedReport
from backend.repositories import shared_report as repo


async def get_user_analysis(db: AsyncSession, analysis_id: int, user_id: int) -> AnalysisResult | None:
    return await repo.get_user_analysis_by_id(db, analysis_id, user_id)


async def get_or_create_shared_report(
    db: AsyncSession,
    analysis_id: int,
    user_id: int,
    current_time: datetime,
) -> SharedReport:
    share = await repo.get_active_shared_report_by_analysis(db, analysis_id, user_id, current_time)
    if not share:
        share = await repo.create_shared_report(db, user_id, analysis_id)
        await db.commit()
        await db.refresh(share)
    return share


async def get_shared_report(db: AsyncSession, token: str) -> SharedReport | None:
    return await repo.get_shared_report_by_token(db, token)


async def get_analysis_for_share(db: AsyncSession, analysis_id: int) -> AnalysisResult | None:
    return await repo.get_analysis_by_id_public(db, analysis_id)
