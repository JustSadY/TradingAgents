from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult


async def get_last_accepted_analysis(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    asset_type: str,
    last_analysis_id: int | None = None,
    business_as_of: datetime | None = None,
    recorded_as_of: datetime | None = None,
) -> AnalysisResult | None:
    """Return the latest completed, learning-eligible analysis in one tenant scope."""
    normalized_ticker = ticker.upper()
    normalized_asset_type = asset_type.lower()

    if business_as_of is None and recorded_as_of is None and isinstance(last_analysis_id, int):
        candidate = await db.get(AnalysisResult, last_analysis_id)
        if (
            candidate is not None
            and candidate.user_id == user_id
            and candidate.ticker == normalized_ticker
            and candidate.asset_type == normalized_asset_type
            and candidate.status == "completed"
            and candidate.learning_eligible is True
        ):
            return candidate

    query = (
        select(AnalysisResult)
        .where(
            AnalysisResult.ticker == normalized_ticker,
            AnalysisResult.asset_type == normalized_asset_type,
            AnalysisResult.status == "completed",
            AnalysisResult.learning_eligible.is_(True),
        )
        .order_by(AnalysisResult.trade_date.desc(), AnalysisResult.created_at.desc())
        .limit(1)
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    if business_as_of is not None:
        query = query.where(AnalysisResult.trade_date <= business_as_of.date().isoformat())
    if recorded_as_of is not None:
        query = query.where(AnalysisResult.created_at <= recorded_as_of)
    return (await db.execute(query)).scalar_one_or_none()
