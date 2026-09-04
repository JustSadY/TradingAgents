from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from backend.models.analysis import AnalysisResult

_BACKFILL_COLUMNS = (
    AnalysisResult.id,
    AnalysisResult.user_id,
    AnalysisResult.ticker,
    AnalysisResult.trade_date,
    AnalysisResult.signal,
    AnalysisResult.final_decision,
    AnalysisResult.market_report,
    AnalysisResult.reflection,
    AnalysisResult.raw_return,
    AnalysisResult.alpha_return,
    AnalysisResult.holding_days,
)


def _tenant_clause(user_id: int | None):
    return AnalysisResult.user_id == user_id if user_id is not None else AnalysisResult.user_id.is_(None)


def _resolved_learning_columns() -> tuple:
    """Columns used by analyst attribution without loading the full analysis row."""
    from backend.trading_agents.agents.analyst_registry import get_report_fields

    report_columns = tuple(
        getattr(AnalysisResult, field)
        for field in get_report_fields()
        if hasattr(AnalysisResult, field)
    )
    return (
        AnalysisResult.id,
        AnalysisResult.ticker,
        AnalysisResult.trade_date,
        AnalysisResult.market_regime_json,
        AnalysisResult.raw_return,
        AnalysisResult.alpha_return,
        *report_columns,
    )


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
        .options(load_only(*_resolved_learning_columns()))
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
        .options(load_only(*_BACKFILL_COLUMNS))
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
