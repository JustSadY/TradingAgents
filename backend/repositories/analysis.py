from sqlalchemy import desc as _desc
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from backend.models.analysis import AnalysisResult
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.repositories.common import scope_to_user


async def list_historical_analyses(
    db: AsyncSession,
    *,
    user=None,
    ticker: str,
    before_trade_date: str,
    limit: int,
) -> list[AnalysisResult]:
    q = scope_to_user(select(AnalysisResult), AnalysisResult, user)
    q = q.where(AnalysisResult.ticker == ticker).where(
        AnalysisResult.trade_date < before_trade_date
    ).order_by(_desc(AnalysisResult.created_at)).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_analyses(
    db: AsyncSession,
    *,
    user=None,
    ticker: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[AnalysisResult]:
    q = (
        select(AnalysisResult)
        .where(AnalysisResult.status == "completed")
        .options(
            defer(AnalysisResult.bull_history),
            defer(AnalysisResult.bear_history),
            defer(AnalysisResult.investment_debate_history),
            defer(AnalysisResult.risk_debate_history),
        )
        .order_by(_desc(AnalysisResult.created_at))
        .limit(limit)
        .offset(offset)
    )
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    q = scope_to_user(q, AnalysisResult, user)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_previous_signal(db: AsyncSession, *, user_id: int | None, ticker: str, exclude_id: int) -> str | None:
    """Signal of the most recent completed analysis for this ticker, before ``exclude_id``.

    Scoped to ``user_id`` so one user's history never leaks into another's.
    """
    q = (
        select(AnalysisResult.signal)
        .where(
            AnalysisResult.ticker == ticker.upper(),
            AnalysisResult.id != exclude_id,
            AnalysisResult.status == "completed",
        )
        .order_by(_desc(AnalysisResult.created_at))
        .limit(1)
    )
    if user_id is not None:
        q = q.where(AnalysisResult.user_id == user_id)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_analysis_by_id(db: AsyncSession, analysis_id: int, user=None) -> AnalysisResult | None:
    q = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
    q = scope_to_user(q, AnalysisResult, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_latest_analysis(db: AsyncSession, *, user) -> AnalysisResult | None:
    q = (
        select(AnalysisResult)
        .where(AnalysisResult.status == "completed")
        .order_by(_desc(AnalysisResult.created_at))
        .limit(1)
    )
    q = scope_to_user(q, AnalysisResult, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_sentiment_history_by_ticker(db: AsyncSession, ticker: str, user=None):
    q = (
        select(AnalysisResult.trade_date, AnalysisResult.signal)
        .where(AnalysisResult.ticker == ticker)
        .order_by(AnalysisResult.trade_date.asc())
    )
    q = scope_to_user(q, AnalysisResult, user)
    result = await db.execute(q)
    return result.all()


async def list_multi_ticker_analyses(
    db: AsyncSession,
    *,
    user=None,
    limit: int = 20,
    offset: int = 0,
) -> list[MultiTickerAnalysis]:
    q = select(MultiTickerAnalysis).order_by(_desc(MultiTickerAnalysis.created_at)).limit(limit).offset(offset)
    q = scope_to_user(q, MultiTickerAnalysis, user)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_multi_ticker_analysis_by_id(
    db: AsyncSession,
    analysis_id: int,
    user=None,
) -> MultiTickerAnalysis | None:
    q = select(MultiTickerAnalysis).where(MultiTickerAnalysis.id == analysis_id)
    q = scope_to_user(q, MultiTickerAnalysis, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def cleanup_stale_analyses(db: AsyncSession) -> int:
    """Mark analyses that were 'running' when the server last stopped as 'failed'."""
    stmt = update(AnalysisResult).where(AnalysisResult.status == "running").values(status="failed")
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount


async def create_analysis_result(db: AsyncSession, **kwargs) -> AnalysisResult:
    task_id = kwargs.get("task_id")
    if task_id:
        stmt = select(AnalysisResult).where(AnalysisResult.task_id == task_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in kwargs.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await db.commit()
            await db.refresh(existing)
            return existing
    try:
        row = AnalysisResult(**kwargs)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
    except IntegrityError:
        await db.rollback()
        stmt = select(AnalysisResult).where(AnalysisResult.task_id == task_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for k, v in kwargs.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await db.commit()
            await db.refresh(existing)
            return existing
        raise


async def update_analysis_result(db: AsyncSession, row_id: int, **fields) -> AnalysisResult | None:
    stmt = select(AnalysisResult).where(AnalysisResult.id == row_id)
    result = await db.execute(stmt)
    curr = result.scalar_one_or_none()
    if curr:
        for k, v in fields.items():
            if hasattr(curr, k):
                setattr(curr, k, v)
        await db.commit()
    return curr
