"""The migrated schema must match the ORM models.

The test suite runs on SQLite built by `create_all` straight from
`Base.metadata`, and production runs on PostgreSQL built by Alembic. Nothing
compared the two, so they diverged: seven foreign keys to `users` stayed at
NO ACTION where the models declare CASCADE, thirteen declared indexes were
never created, and `config_presets` never got its uniqueness. Deleting a user
who had saved settings failed on PostgreSQL and passed here.

This test closes that gap, but it needs a real PostgreSQL to migrate into and
so cannot run against the default SQLite suite. Point it at a throwaway
database — it drops and recreates the schema it is given:

    MIGRATION_DRIFT_DATABASE_URL=postgresql+asyncpg://postgres@localhost/ta_drift \\
        uv run pytest tests/test_core/test_migration_drift.py

The database needs the `vector` extension available, since revision
7f8091a2b3c4 refuses to run without it.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DRIFT_URL = os.getenv("MIGRATION_DRIFT_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DRIFT_URL,
    reason="set MIGRATION_DRIFT_DATABASE_URL to a throwaway PostgreSQL database to run",
)


@pytest.fixture(scope="module")
async def migrated_database() -> str:
    """A database at Alembic head, built the way a deployment builds one."""
    from alembic.config import Config
    from sqlalchemy.ext.asyncio import create_async_engine

    from alembic import command

    engine = create_async_engine(DRIFT_URL)
    async with engine.begin() as connection:
        await connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await connection.exec_driver_sql("CREATE SCHEMA public")
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    await engine.dispose()

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # `env.py` reads this first, so the app's own DATABASE_URL is left alone.
    os.environ["MIGRATION_DATABASE_URL"] = DRIFT_URL
    # `env.py` ends in `asyncio.run(...)`, which cannot nest inside the loop
    # this fixture already runs on, so give it a thread with no loop of its own.
    await asyncio.to_thread(command.upgrade, config, "head")
    return DRIFT_URL


async def test_models_and_migrations_describe_the_same_schema(migrated_database: str):
    """`alembic check`, as an assertion rather than a command."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.core.database import Base
    from backend.core.migration_policy import include_object

    def compare(connection):
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True, "include_object": include_object},
        )
        return compare_metadata(context, Base.metadata)

    engine = create_async_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(compare)
    finally:
        await engine.dispose()

    assert differences == [], (
        "The migrated schema differs from the models. Every difference here is "
        "something production has and the test suite does not, or vice versa."
    )


async def test_every_user_foreign_key_cascades(migrated_database: str):
    """A user must be deletable without clearing each child table by hand.

    `delete_user_and_emit` clears six tables explicitly for the sake of older
    installations, but it does not know about the rest — so anything left at
    NO ACTION blocks the delete outright.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            result = await connection.exec_driver_sql(
                """
                -- `confdeltype` is PostgreSQL's "char" type; asyncpg hands that back
                -- as bytes, so cast it to text rather than comparing b'c' to 'c'.
                SELECT c.conrelid::regclass::text, c.conname, c.confdeltype::text
                FROM pg_constraint c
                WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass
                """
            )
            rows = result.all()
    finally:
        await engine.dispose()

    assert rows, "no foreign keys to users found — the query or schema is wrong"

    # 'c' cascades, 'n' sets null. Both delete cleanly; 'a' (NO ACTION) does not.
    blocking = [(table, name) for table, name, action in rows if action not in {"c", "n"}]

    assert blocking == []
