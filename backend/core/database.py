import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import Numeric, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
_logger = logging.getLogger(__name__)

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


def _alembic_config():
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


async def _run_alembic(command_name: str, revision: str) -> None:
    """Run Alembic's synchronous command API off the event loop."""
    from alembic import command

    fn = getattr(command, command_name)
    await asyncio.to_thread(fn, _alembic_config(), revision)


async def _has_legacy_app_tables(conn) -> bool:
    """Whether an unversioned PostgreSQL database already contains app data."""
    return bool((await conn.execute(text("SELECT to_regclass('public.users')"))).scalar_one_or_none())


async def create_all_tables():
    """Bring the schema to the current Alembic head before serving requests.

    SQLAlchemy ``create_all`` cannot alter existing tables, so treating an
    existing ``alembic_version`` table as a reason to return silently meant
    every later migration was skipped.  PostgreSQL deployments now use
    Alembic exclusively.  SQLite remains a lightweight development/test
    fallback because the production migrations intentionally use PostgreSQL
    foreign-key and index operations.
    """
    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            from backend.core.migrations import apply_column_migrations, apply_type_migrations

            await apply_column_migrations(conn)
            await apply_type_migrations(conn)
        return

    async with engine.begin() as conn:
        has_version = await _has_alembic_version(conn)
        legacy_schema = not has_version and await _has_legacy_app_tables(conn)

    if legacy_schema:
        # Older installations were created with create_all and never had a
        # migration history.  Stamp the baseline only; upgrading from there
        # still runs every subsequent migration instead of pretending they
        # were already applied.
        _logger.warning("Detected unversioned legacy schema; stamping Alembic baseline before upgrade.")
        await _run_alembic("stamp", "89f1a049b357")

    try:
        await _run_alembic("upgrade", "head")
    except Exception:
        _logger.exception("Alembic upgrade failed; refusing to start with an unknown schema state")
        raise
