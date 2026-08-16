from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.refresh_session import RefreshSession


async def create_refresh_session(
    db: AsyncSession,
    *,
    session_id: str,
    user_id: int,
    current_jti_hash: str,
    expires_at: datetime,
) -> RefreshSession:
    session = RefreshSession(
        id=session_id,
        user_id=user_id,
        current_jti_hash=current_jti_hash,
        expires_at=expires_at,
    )
    db.add(session)
    await db.flush()
    return session


async def get_refresh_session_for_update(db: AsyncSession, session_id: str) -> RefreshSession | None:
    result = await db.execute(
        select(RefreshSession).where(RefreshSession.id == session_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def delete_refresh_sessions_for_user(db: AsyncSession, user_id: int) -> None:
    await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))
