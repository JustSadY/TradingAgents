from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.user import User


async def list_active_analysis_task_ids(db: AsyncSession, user_id: int) -> list[str]:
    result = await db.execute(
        select(AnalysisResult.task_id).where(
            AnalysisResult.user_id == user_id,
            AnalysisResult.status.in_(("queued", "running")),
            AnalysisResult.task_id.is_not(None),
        )
    )
    return [task_id for task_id in result.scalars().all() if task_id]


async def delete_user_record(db: AsyncSession, user: User) -> None:
    await db.delete(user)
    await db.commit()
