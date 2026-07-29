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

# Tables created by the Alembic baseline revision (89f1a049b357).  An older
# installation created through ``create_all`` has no alembic_version row, so
# it must be stamped before it can receive later revisions.  Never stamp a
# partial schema: that would record a baseline it does not actually satisfy
# and turn missing-table failures into a much harder recovery problem.
_BASELINE_APP_TABLES = frozenset(
    {
        "agent_settings",
        "agent_tool_settings",
        "analysis_chats",
        "analysis_results",
        "analyst_report_cache",
        "app_settings",
        "assistant_messages",
        "config_presets",
        "holdings",
        "market_daily_summaries",
        "multi_ticker_analyses",
        "news_analysis_cache",
        "news_cache",
        "orders",
        "portfolios",
        "price_alerts",
        "shared_reports",
        "system_logs",
        "system_settings",
        "trade_notes",
        "user_agent_access",
        "user_page_permissions",
        "user_personas",
        "user_setting_permissions",
        "user_tool_access",
        "user_tool_field_access",
        "users",
        "webhook_deliveries",
    }
)


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
    # Alembic stores options in a configparser that performs %-interpolation, so
    # a percent sign in the URL (a percent-encoded password, typically) is read
    # as a broken placeholder.  Doubling it is how configparser escapes a literal
    # percent; get_main_option() hands the original URL back.
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    return cfg


async def _run_alembic(command_name: str, revision: str) -> None:
    """Run Alembic's synchronous command API off the event loop."""
    from alembic import command

    fn = getattr(command, command_name)
    await asyncio.to_thread(fn, _alembic_config(), revision)


def _is_complete_unversioned_app_schema(table_names: set[str]) -> bool:
    """Return whether *table_names* can safely be stamped at the baseline.

    A fresh database contains no application tables and should receive the
    baseline via ``alembic upgrade head``.  A partial database cannot safely
    be stamped because the baseline would falsely claim tables already exist.
    """
    existing = table_names.intersection(_BASELINE_APP_TABLES)
    if not existing:
        return False

    missing = _BASELINE_APP_TABLES.difference(existing)
    if missing:
        raise RuntimeError(
            "Refusing to stamp a partial unversioned Paperclip schema. "
            f"Found application tables: {', '.join(sorted(existing))}; "
            f"missing baseline tables: {', '.join(sorted(missing))}. "
            "Restore or complete the old schema, verify a backup, then stamp "
            "the Alembic baseline explicitly."
        )
    return True


async def _has_complete_unversioned_app_schema(conn) -> bool:
    """Inspect the active PostgreSQL schema before an automatic baseline stamp."""
    rows = await conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
    )
    return _is_complete_unversioned_app_schema(set(rows.scalars()))


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
            from backend.core.migrations import (
                apply_column_migrations,
                apply_type_migrations,
                normalize_sqlite_analysis_signals,
                normalize_sqlite_settings_collections,
                normalize_sqlite_simulation_entry_commissions,
            )

            await apply_column_migrations(conn)
            await apply_type_migrations(conn)
            await normalize_sqlite_analysis_signals(conn)
            await normalize_sqlite_settings_collections(conn)
            await normalize_sqlite_simulation_entry_commissions(conn)
        return

    async with engine.begin() as conn:
        has_version = await _has_alembic_version(conn)
        legacy_schema = not has_version and await _has_complete_unversioned_app_schema(conn)

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
