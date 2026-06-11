"""Unit and integration tests for user-based logging features."""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.core.log_handler import DatabaseLogHandler, current_user_id
from backend.core.migrations import apply_column_migrations, apply_type_migrations
from backend.models.log import SystemLog
from backend.models.user import User
from backend.schemas.log import LogRead


@pytest_asyncio.fixture
async def db():
    # Setup test database and run both Base.create_all and our migrations
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_column_migrations(conn)
        await apply_type_migrations(conn)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_migrations_applied_user_id_column(db):
    # Verify SystemLog table has user_id column after migrations
    res = await db.execute(select(SystemLog).limit(1))
    # Should not raise an exception, indicating columns are present
    assert res is not None


@pytest.mark.asyncio
async def test_log_handler_captures_user_id_from_contextvar(db, monkeypatch):
    # Setup a dedicated log handler to avoid global side-effects
    handler = DatabaseLogHandler()
    
    # Mock AsyncSessionLocal used by the worker to use our test db fixture
    fake_sessionmaker = MagicMock()
    fake_sessionmaker.return_value.__aenter__.return_value = db
    fake_sessionmaker.return_value.__aexit__.return_value = None
    monkeypatch.setattr("backend.core.database.AsyncSessionLocal", fake_sessionmaker)

    await handler.start()
    
    try:
        # Set user context
        token = current_user_id.set(42)
        
        # Emit log
        record = logging.LogRecord(
            name="test_source",
            level=logging.INFO,
            pathname="test_path.py",
            lineno=10,
            msg="test user log message",
            args=(),
            exc_info=None
        )
        handler.emit(record)
        
        # Wait a short moment and trigger a flush by stopping the handler worker
        current_user_id.reset(token)
    finally:
        handler.stop()
        # Wait for worker task to complete flush
        if handler._task:
            try:
                await asyncio.wait_for(handler._task, timeout=2.0)
            except Exception:
                pass

    # Verify log entry in DB has user_id = 42
    res = await db.execute(select(SystemLog).where(SystemLog.message == "test user log message"))
    entry = res.scalar_one_or_none()
    assert entry is not None
    assert entry.user_id == 42


@pytest.mark.asyncio
async def test_log_handler_captures_user_id_from_extra(db, monkeypatch):
    handler = DatabaseLogHandler()
    
    fake_sessionmaker = MagicMock()
    fake_sessionmaker.return_value.__aenter__.return_value = db
    fake_sessionmaker.return_value.__aexit__.return_value = None
    monkeypatch.setattr("backend.core.database.AsyncSessionLocal", fake_sessionmaker)

    await handler.start()
    
    try:
        # Emit log with user_id in extra
        record = logging.LogRecord(
            name="test_source",
            level=logging.INFO,
            pathname="test_path.py",
            lineno=10,
            msg="test extra log message",
            args=(),
            exc_info=None
        )
        record.user_id = 99  # Set via extra
        handler.emit(record)
    finally:
        handler.stop()
        if handler._task:
            try:
                await asyncio.wait_for(handler._task, timeout=2.0)
            except Exception:
                pass

    # Verify log entry in DB has user_id = 99
    res = await db.execute(select(SystemLog).where(SystemLog.message == "test extra log message"))
    entry = res.scalar_one_or_none()
    assert entry is not None
    assert entry.user_id == 99


@pytest.mark.asyncio
async def test_list_my_logs_filtering(db):
    # Insert logs for different users
    log1 = SystemLog(level="INFO", source="test", message="user 1 log", user_id=1)
    log2 = SystemLog(level="INFO", source="test", message="user 2 log", user_id=2)
    log3 = SystemLog(level="INFO", source="test", message="system log", user_id=None)
    db.add_all([log1, log2, log3])
    await db.commit()

    # Import route logic or mock it
    from backend.repositories.common import scope_to_user

    # Mock users
    user_1 = User(id=1, username="user1", role="user")
    user_admin = User(id=3, username="admin", role="admin")

    # Scoped query for User 1
    q1 = select(SystemLog)
    q1 = scope_to_user(q1, SystemLog, user_1)
    res1 = (await db.execute(q1)).scalars().all()
    assert len(res1) == 1
    assert res1[0].message == "user 1 log"

    # Scoped query for Admin (should see everything)
    q_admin = select(SystemLog)
    q_admin = scope_to_user(q_admin, SystemLog, user_admin)
    res_admin = (await db.execute(q_admin)).scalars().all()
    assert len(res_admin) == 3
