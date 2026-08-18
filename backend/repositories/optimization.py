"""Persistence for strategy parameter searches."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.optimization import OptimizationRun
from backend.repositories.common import scope_to_user


async def create_optimization_run(
    db: AsyncSession,
    *,
    user_id: int | None,
    ticker: str,
    strategy_type: str,
    objective: str,
    start_date: str,
    end_date: str,
    trials_requested: int,
) -> OptimizationRun:
    run = OptimizationRun(
        user_id=user_id,
        ticker=ticker.upper(),
        strategy_type=strategy_type,
        objective=objective,
        start_date=start_date,
        end_date=end_date,
        trials_requested=trials_requested,
        status="running",
    )
    db.add(run)
    await db.flush()
    return run


async def complete_optimization_run(db: AsyncSession, run: OptimizationRun, result: dict) -> OptimizationRun:
    run.status = "completed"
    run.trials_completed = int(result.get("trials_completed") or 0)
    run.best_params = result.get("best_params")
    run.best_value = result.get("best_value")
    run.best_metrics = result.get("best_metrics")
    run.baseline_params = result.get("baseline_params")
    run.baseline_value = result.get("baseline_value")
    run.baseline_metrics = result.get("baseline_metrics")
    run.trials = result.get("trials")
    run.completed_at = datetime.now(UTC)
    await db.flush()
    return run


async def fail_optimization_run(db: AsyncSession, run: OptimizationRun, error: str) -> OptimizationRun:
    run.status = "failed"
    # Truncated: the column is Text, but a pathological driver error should not
    # become the largest row in the table.
    run.error = str(error)[:4000]
    run.completed_at = datetime.now(UTC)
    await db.flush()
    return run


async def list_optimization_runs(
    db: AsyncSession,
    user,
    *,
    ticker: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[OptimizationRun]:
    query = select(OptimizationRun).order_by(desc(OptimizationRun.created_at)).limit(limit).offset(offset)
    if ticker:
        query = query.where(OptimizationRun.ticker == ticker.upper())
    query = scope_to_user(query, OptimizationRun, user)
    return list((await db.execute(query)).scalars().all())


async def get_optimization_run(db: AsyncSession, run_id: int, user) -> OptimizationRun | None:
    query = select(OptimizationRun).where(OptimizationRun.id == run_id)
    query = scope_to_user(query, OptimizationRun, user)
    return (await db.execute(query)).scalar_one_or_none()
