from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.models.analysis import AnalysisResult

_DECISION_COLUMNS = (
    AnalysisResult.id,
    AnalysisResult.portfolio_decision_json,
)


def _base_last_accepted_query(*, user_id: int | None, ticker: str, asset_type: str):
    query = (
        select(AnalysisResult)
        .where(
            AnalysisResult.ticker == ticker,
            AnalysisResult.asset_type == asset_type,
            AnalysisResult.status == "completed",
            AnalysisResult.learning_eligible.is_(True),
        )
        .options(load_only(*_DECISION_COLUMNS))
    )
    if user_id is None:
        return query.where(AnalysisResult.user_id.is_(None))
    return query.where(AnalysisResult.user_id == user_id)


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
    """Return the latest accepted decision in one tenant scope.

    Callers consume only ``portfolio_decision_json``. Keep report text, debate
    histories and strategy snapshots off this pre-graph lookup, including the
    primary-key fast path.
    """
    normalized_ticker = ticker.upper()
    normalized_asset_type = asset_type.lower()
    base_query = _base_last_accepted_query(
        user_id=user_id,
        ticker=normalized_ticker,
        asset_type=normalized_asset_type,
    )

    if business_as_of is None and recorded_as_of is None and isinstance(last_analysis_id, int):
        candidate = (
            await db.execute(
                base_query.where(AnalysisResult.id == last_analysis_id).limit(1)
            )
        ).scalar_one_or_none()
        if candidate is not None:
            return candidate

    query = base_query.order_by(AnalysisResult.trade_date.desc(), AnalysisResult.created_at.desc()).limit(1)
    if business_as_of is not None:
        query = query.where(AnalysisResult.trade_date <= business_as_of.date().isoformat())
    if recorded_as_of is not None:
        query = query.where(AnalysisResult.created_at <= recorded_as_of)
    return (await db.execute(query)).scalar_one_or_none()
