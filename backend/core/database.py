import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import Numeric, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()
engine_kwargs = {"echo": False, "pool_pre_ping": True}
if "sqlite" not in settings.DATABASE_URL:
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
    )
engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)
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
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    return cfg


async def _run_alembic(command_name: str, revision: str) -> None:
    """Run Alembic's synchronous command API off the event loop."""
    from alembic import command

    fn = getattr(command, command_name)
    await asyncio.to_thread(fn, _alembic_config(), revision)


def _expected_alembic_heads() -> set[str]:
    from alembic.script import ScriptDirectory

    return set(ScriptDirectory.from_config(_alembic_config()).get_heads())


async def _verify_schema_at_alembic_head() -> None:
    async with engine.connect() as conn:
        if not await _has_alembic_version(conn):
            raise RuntimeError(
                "Production database is not Alembic-managed. Run `alembic -c backend/alembic.ini upgrade head` "
                "with the migration role before starting the application."
            )
        rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current = set(rows.scalars())

    expected = _expected_alembic_heads()
    if current != expected:
        raise RuntimeError(
            "Production database schema is not at Alembic head: "
            f"current={sorted(current)}, expected={sorted(expected)}. "
            "Run the migration step before starting web/worker processes."
        )


async def create_all_tables():
    """Bring the schema to the current Alembic head before serving requests."""
    import backend.models  # noqa: F401

    if engine.dialect.name == "sqlite":
        # SQLite is a development and test convenience only; PostgreSQL is the
        # supported database and Alembic is its sole schema authority. Build the
        # schema straight from the ORM metadata. There is deliberately no
        # catch-up layer for an existing SQLite file — delete it and let this
        # recreate it.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    if settings.ENVIRONMENT.strip().lower() == "production":
        await _verify_schema_at_alembic_head()
        from backend.core.rls import verify_runtime_rls_role

        await verify_runtime_rls_role(engine)
        return

    try:
        await _run_alembic("upgrade", "head")
        from backend.core.rls import verify_runtime_rls_role

        await verify_runtime_rls_role(engine)
    except Exception:
        _logger.exception("Alembic upgrade or RLS runtime-role validation failed; refusing unknown database security state")
        raise
