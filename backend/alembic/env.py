"""Alembic migration environment (async).

Reads the app's DATABASE_URL from settings and uses the project's
``Base.metadata`` as the autogenerate target, so ``alembic revision
--autogenerate`` diffs the live schema against the SQLAlchemy models.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make ``import backend...`` work no matter the current working directory.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import backend.models  # noqa: E402,F401  (importing registers every table on Base.metadata)
from backend.core.config import get_settings  # noqa: E402
from backend.core.database import Base  # noqa: E402

config = context.config

# ``fileConfig`` unconditionally replaces the root logger's handler list with
# whatever alembic.ini's own ``[handler_console]`` defines — regardless of
# ``disable_existing_loggers``. The web app runs migrations in-process on
# every startup (``core/database.py::create_all_tables``), after it has
# already attached its own handlers (console, rotating file, and notably
# ``DatabaseLogHandler``, which persists system logs to the DB for the
# Logs page). Calling fileConfig there silently detaches all of them —
# journalctl keeps working because alembic's replacement handler still
# writes to stderr, but system_logs stops receiving rows forever, with no
# error anywhere. Only apply alembic.ini's logging config for a standalone
# ``alembic`` CLI invocation, where the root logger has nothing configured
# yet.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

# Standalone migrations may use a privileged URL supplied only to the migration
# process. The web/worker processes never need that credential. Without the
# override (development/tests), Alembic uses the normal application URL.
migration_url = os.getenv("MIGRATION_DATABASE_URL", "").strip() or get_settings().DATABASE_URL
if migration_url.startswith("postgresql://"):
    migration_url = "postgresql+asyncpg://" + migration_url.removeprefix("postgresql://")
elif migration_url.startswith("postgres://"):
    migration_url = "postgresql+asyncpg://" + migration_url.removeprefix("postgres://")
# ``%`` is doubled because configparser treats percent-encoded passwords as interpolation.
config.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection (alembic upgrade --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
