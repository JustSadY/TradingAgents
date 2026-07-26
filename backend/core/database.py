from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import Numeric, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

MONEY = Numeric(20, 8, asdecimal=True)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _has_alembic_version(conn) -> bool:
    if conn.dialect.name == "sqlite":
        row = (
            await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"))
        ).fetchone()
        return row is not None
    row = (await conn.execute(text("SELECT to_regclass('public.alembic_version')"))).scalar_one_or_none()
    return row is not None


async def _stamp_alembic_head(conn) -> None:
    _alembic_cfg = None
    try:
        from alembic.config import Config
        from alembic import command
        ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        _alembic_cfg = Config(str(ini_path))
        _alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        command.stamp(_alembic_cfg, "head")
    except Exception:
        pass


_ALEMBIC_STAMPED: bool = False


async def create_all_tables():
    global _ALEMBIC_STAMPED
    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("SET LOCAL statement_timeout = 0"))
            await conn.execute(text("SET LOCAL lock_timeout = 0"))
        await conn.run_sync(Base.metadata.create_all)
        if await _has_alembic_version(conn):
            return
        from backend.core.migrations import apply_column_migrations, apply_type_migrations

        await apply_column_migrations(conn)
        await apply_type_migrations(conn)
    if not _ALEMBIC_STAMPED:
        async with engine.begin() as conn:
            if not await _has_alembic_version(conn):
                await _stamp_alembic_head(conn)
            _ALEMBIC_STAMPED = True
