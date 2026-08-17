from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult


def _tenant_clause(user_id: int | None):
    return AnalysisResult.user_id == user_id if user_id is not None else AnalysisResult.user_id.is_(None)


async def list_resolved_learning_analyses(
    db: AsyncSession,
    *,
    user_id: int | None,
) -> list[AnalysisResult]:
    """Return completed outcome-known rows in exactly one tenant/system scope."""
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.isnot(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .where(AnalysisResult.status == "completed")
        .where(_tenant_clause(user_id))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_return_backfill_candidates(
    db: AsyncSession,
    *,
    cutoff_trade_date: str,
    limit: int = 50,
) -> list[AnalysisResult]:
    """Return completed analyses whose realized outcome is ready to backfill."""
    query = (
        select(AnalysisResult)
        .where(AnalysisResult.raw_return.is_(None))
        .where(AnalysisResult.signal.isnot(None))
        .where(AnalysisResult.learning_eligible.is_(True))
        .where(AnalysisResult.status == "completed")
        .where(AnalysisResult.trade_date <= cutoff_trade_date)
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


def apply_return_outcome(
    row: AnalysisResult,
    *,
    raw_return: float,
    alpha_return: float | None,
    holding_days: int | None,
) -> None:
    """Apply already-computed outcome values to one persisted analysis row."""
    row.raw_return = raw_return
    row.alpha_return = alpha_return
    row.holding_days = holding_days


def apply_reflection(row: AnalysisResult, reflection: str) -> None:
    """Apply an already-generated reflection to one analysis row."""
    row.reflection = reflection
