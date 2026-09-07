from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.models.analysis import AnalysisResult

_STATS_COLUMNS = (
    AnalysisResult.id,
    AnalysisResult.preset_name,
    AnalysisResult.llm_provider,
    AnalysisResult.llm_model,
    AnalysisResult.duration_seconds,
    AnalysisResult.tokens_in,
    AnalysisResult.tokens_out,
    AnalysisResult.signal,
    AnalysisResult.raw_return,
    AnalysisResult.alpha_return,
    AnalysisResult.created_at,
)
_CALIBRATION_COLUMNS = (
    AnalysisResult.id,
    AnalysisResult.signal,
    AnalysisResult.portfolio_decision_json,
    AnalysisResult.raw_return,
    AnalysisResult.alpha_return,
)


def _prefilter_columns() -> tuple:
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    report_columns = tuple(
        getattr(AnalysisResult, field)
        for field in get_report_fields()
        if hasattr(AnalysisResult, field)
    )
    return AnalysisResult.id, AnalysisResult.raw_return, *report_columns


async def list_recent_run_token_totals(
    db: AsyncSession,
    *,
    user_id: int,
    limit: int = 10,
) -> list[int]:
    """Total tokens spent by this user's most recent completed analyses.

    The pre-run estimate is built from these rather than from a per-analyst
    constant: the numbers are the provider's own counts for this account's own
    configuration, so they track a changed model, analyst set or debate depth
    on their own instead of being maintained by hand.
    """
    query = (
        select(AnalysisResult.tokens_in, AnalysisResult.tokens_out)
        .where(
            AnalysisResult.status == "completed",
            AnalysisResult.user_id == user_id,
        )
        .order_by(AnalysisResult.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    totals = [int(tokens_in or 0) + int(tokens_out or 0) for tokens_in, tokens_out in rows]
    return [total for total in totals if total > 0]


async def list_completed_analyses_for_stats(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    ticker: str | None = None,
    require_raw_return: bool = False,
) -> list[AnalysisResult]:
    # A/B and signal-performance views use only compact run metrics. Analyst
    # reports, debate histories and strategy JSON never participate here.
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.status == "completed")
        .options(load_only(*_STATS_COLUMNS))
    )
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
    # Confidence calibration consumes only the accepted decision, fallback
    # signal and realized raw/alpha outcome.
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.alpha_return.is_not(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .options(load_only(*_CALIBRATION_COLUMNS))
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    if asset_type:
        query = query.where(AnalysisResult.asset_type == asset_type)
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_learning_eligible_ticker_analyses(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
) -> list[AnalysisResult]:
    """Return outcome-known, learning-eligible history for one ticker/tenant."""
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.ticker == ticker.upper())
        .where(AnalysisResult.raw_return.is_not(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .options(load_only(*_prefilter_columns()))
    )
    if user_id is None:
        query = query.where(AnalysisResult.user_id.is_(None))
    else:
        query = query.where(AnalysisResult.user_id == user_id)
    result = await db.execute(query)
    return list(result.scalars().all())
