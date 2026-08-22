"""Retention boundaries for tables nothing used to delete from.

``system_logs`` and ``refresh_sessions`` both grew without bound: an analysis
writes hundreds of INFO rows, and every sign-in left a session row behind even
after it expired or was revoked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from backend.core.database import AsyncSessionLocal
from backend.models.log import SystemLog
from backend.models.refresh_session import RefreshSession
from backend.models.user import User
from backend.services.maintenance_service import cleanup_transient_data

_MARKER = "retention-boundary-test"


@pytest.fixture
async def seeded(test_engine):
    """Commit rows the cleanup job can see, then take them away again.

    The job opens its own session, so rows written inside the per-test
    transaction would be invisible to it.
    """
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        user = User(
            username=_MARKER,
            hashed_password="x",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        db.add_all(
            [
                SystemLog(level="INFO", source=_MARKER, message="old", created_at=now - timedelta(days=60)),
                SystemLog(level="INFO", source=_MARKER, message="fresh", created_at=now),
                RefreshSession(
                    id=f"{_MARKER}-expired",
                    user_id=user.id,
                    current_jti_hash="a",
                    expires_at=now - timedelta(days=3),
                ),
                RefreshSession(
                    id=f"{_MARKER}-revoked",
                    user_id=user.id,
                    current_jti_hash="b",
                    expires_at=now + timedelta(days=7),
                    revoked_at=now - timedelta(days=3),
                ),
                RefreshSession(
                    id=f"{_MARKER}-live",
                    user_id=user.id,
                    current_jti_hash="c",
                    expires_at=now + timedelta(days=7),
                ),
            ]
        )
        await db.commit()
        user_id = user.id

    yield user_id

    async with AsyncSessionLocal() as db:
        await db.execute(delete(SystemLog).where(SystemLog.source == _MARKER))
        await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _remaining(model, column, value) -> list:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(model).where(column == value))).scalars().all()


@pytest.mark.asyncio
async def test_cleanup_drops_dead_refresh_sessions_and_keeps_the_live_one(seeded):
    await cleanup_transient_data()

    remaining = await _remaining(RefreshSession, RefreshSession.user_id, seeded)
    assert [session.id for session in remaining] == [f"{_MARKER}-live"]


@pytest.mark.asyncio
async def test_cleanup_trims_system_logs_to_the_configured_window(seeded):
    await cleanup_transient_data()

    remaining = await _remaining(SystemLog, SystemLog.source, _MARKER)
    assert [row.message for row in remaining] == ["fresh"]


@pytest.mark.asyncio
async def test_zero_retention_keeps_every_system_log(seeded, monkeypatch):
    from backend.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "SYSTEM_LOG_RETENTION_DAYS", 0, raising=False)

    await cleanup_transient_data()

    remaining = await _remaining(SystemLog, SystemLog.source, _MARKER)
    assert sorted(row.message for row in remaining) == ["fresh", "old"]
