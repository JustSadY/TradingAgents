from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)


async def create_skeleton_result(
    db: AsyncSession,
    task_id: str,
    ticker: str,
    trade_date: str,
    asset_type: str,
    triggered_by: str,
    user_id: int | None = None,
) -> AnalysisResult:
    """Create the initial skeleton record for tracking progress."""
    from backend.repositories.analysis import create_analysis_result

    return await create_analysis_result(
        db,
        task_id=task_id,
        user_id=user_id,
        ticker=ticker,
        trade_date=trade_date,
        asset_type=asset_type,
        status="running",
        triggered_by=triggered_by,
    )


async def update_result_fields(db: AsyncSession, row_id: int, **fields) -> None:
    """Incrementally update an analysis result record."""
    from backend.repositories.analysis import update_analysis_result

    await update_analysis_result(db, row_id, **fields)


async def finalize_result(db: AsyncSession, row_id: int, **final_data) -> None:
    """Mark the analysis as completed and save final reports/stats."""
    final_data["status"] = "completed"
    await update_result_fields(db, row_id, **final_data)


async def mark_as_failed(db: AsyncSession, row_id: int) -> None:
    """Mark the analysis as failed."""
    await update_result_fields(db, row_id, status="failed")


async def mark_as_cancelled(db: AsyncSession, row_id: int) -> None:
    """Mark the analysis as cancelled."""
    await update_result_fields(db, row_id, status="cancelled")
