from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult

async def get_token_usage_rows(db: AsyncSession, user_id: int) -> list:
    q = (
        select(
            AnalysisResult.llm_provider,
            AnalysisResult.llm_model,
            func.coalesce(func.sum(AnalysisResult.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AnalysisResult.tokens_out), 0).label("tokens_out"),
            func.count(AnalysisResult.id).label("analyses"),
        )
        .where(
            AnalysisResult.user_id == user_id,
            AnalysisResult.status == "completed",
        )
        .group_by(AnalysisResult.llm_provider, AnalysisResult.llm_model)
    )
    result = await db.execute(q)
    return result.all()

async def get_daily_token_usage_rows(db: AsyncSession, user_id: int, limit: int = 30) -> list:
    q = (
        select(
            func.date(AnalysisResult.created_at).label("day"),
            func.coalesce(func.sum(AnalysisResult.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AnalysisResult.tokens_out), 0).label("tokens_out"),
            func.count(AnalysisResult.id).label("analyses"),
        )
        .where(
            AnalysisResult.user_id == user_id,
            AnalysisResult.status == "completed",
        )
        .group_by(func.date(AnalysisResult.created_at))
        .order_by(func.date(AnalysisResult.created_at))
        .limit(limit)
    )
    result = await db.execute(q)
    return result.all()
