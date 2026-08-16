"""Does tenant isolation survive replacing the identity provider?

This is the question the PoC exists to answer, and it cannot be answered on
SQLite: the isolation is a PostgreSQL row-level security policy, and the whole
argument for the design is that the policy never learns the provider changed.

So this migrates a throwaway database to Alembic head, binds a session through
the SuperTokens bridge exactly as a request would, and then reads a real tenant
table to see what the database actually returns.

    MIGRATION_DRIFT_DATABASE_URL=postgresql+asyncpg://postgres@localhost/ta_poc \\
        uv run pytest tests/test_poc/test_supertokens_rls.py

It reuses the drift test's variable because it wants the same thing: a database
it is allowed to drop and recreate. It needs the `vector` extension available,
since revision 7f8091a2b3c4 refuses to run without it.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.poc.supertokens.bridge import IdentityMappingError, tenant_from_supertokens_session

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

    from alembic import command

    engine = create_async_engine(DRIFT_URL)
    async with engine.begin() as connection:
        await connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await connection.exec_driver_sql("CREATE SCHEMA public")
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    await engine.dispose()

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    os.environ["MIGRATION_DATABASE_URL"] = DRIFT_URL
    # `env.py` ends in `asyncio.run(...)`, which cannot nest inside this loop.
    await asyncio.to_thread(command.upgrade, config, "head")
    return DRIFT_URL


RUNTIME_ROLE = "ta_poc_runtime"


def _as_role(url: str, role: str) -> str:
    """The same database, connected as a different role."""
    return str(make_url(url).set(username=role, password=role))


@pytest.fixture(scope="module")
async def runtime_url(migrated_database: str) -> str:
    """A role that RLS actually applies to.

    PostgreSQL exempts superusers and table owners from row-level security, so
    a test that connects as the migrating role proves nothing at all — every
    policy in the schema is simply skipped, and every tenant sees every row.

    ``deploy/provision-postgres-roles.sh`` is where the real deployment deals
    with this: it provisions a schema-owning migrator and a separate runtime
    role created ``NOSUPERUSER ... NOBYPASSRLS`` holding only DML grants. This
    reproduces that split, because the split is what makes the isolation real.
    """
    # asyncpg sends one statement per call, so these cannot be a single script.
    statements = [
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
                CREATE ROLE {RUNTIME_ROLE} LOGIN PASSWORD '{RUNTIME_ROLE}';
            END IF;
        END $$
        """,
        f"ALTER ROLE {RUNTIME_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS",
        f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE}",
    ]
    engine = create_async_engine(migrated_database)
    async with engine.begin() as connection:
        for statement in statements:
            await connection.exec_driver_sql(statement)
    await engine.dispose()
    return _as_role(migrated_database, RUNTIME_ROLE)


@pytest.fixture
async def seeded(migrated_database: str, runtime_url: str):
    """Two tenants, each owning one preset, plus an admin.

    Seeded as the owning role, which bypasses RLS — that is how a migration or
    an admin tool would write. The engine handed to the tests is the runtime
    role, so the reads are the part under test.
    """
    engine = create_async_engine(migrated_database)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))
        await connection.execute(
            text(
                """
                INSERT INTO users (id, username, hashed_password, is_active, role, created_at)
                VALUES (1, 'alice', 'x', true, 'user',  now()),
                       (2, 'bob',   'x', true, 'user',  now()),
                       (3, 'root',  'x', true, 'admin', now())
                """
            )
        )
        await connection.execute(
            text(
                """
                INSERT INTO config_presets (user_id, name, description, settings_json, created_at)
                VALUES (1, 'alice-preset', '', '{}', now()),
                       (2, 'bob-preset',   '', '{}', now())
                """
            )
        )
    await engine.dispose()

    engine = create_async_engine(runtime_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _preset_names(session: AsyncSession) -> list[str]:
    rows = await session.execute(text("SELECT name FROM config_presets ORDER BY name"))
    return [name for (name,) in rows.all()]


async def test_a_supertokens_session_sees_only_its_own_tenants_rows(seeded):
    """The whole claim, checked against the database rather than argued.

    Nothing in the policy, the migrations, or the 700-odd `user_id` call sites
    knows that a SuperTokens session is what established this context.
    """
    async with AsyncSession(bind=seeded) as session:
        # "1" is what a verified session yields once createUserIdMapping has
        # registered the application's users.id as the external user id.
        user = await tenant_from_supertokens_session(session, "1")
        assert user.username == "alice"

        assert await _preset_names(session) == ["alice-preset"]


async def test_switching_the_bound_session_switches_the_visible_tenant(seeded):
    async with AsyncSession(bind=seeded) as session:
        await tenant_from_supertokens_session(session, "2")
        assert await _preset_names(session) == ["bob-preset"]


async def test_an_admin_session_still_bypasses_tenant_policies(seeded):
    """`app.is_admin` is the flag that disables isolation schema-wide.

    Worth asserting explicitly: if the bridge had taken the admin decision from
    SuperTokens instead of from `users.role`, this is the blast radius.
    """
    async with AsyncSession(bind=seeded) as session:
        user = await tenant_from_supertokens_session(session, "3")
        assert user.is_admin

        assert await _preset_names(session) == ["alice-preset", "bob-preset"]


async def test_an_unmapped_session_never_reaches_a_query(seeded):
    """A SuperTokens user with no ID mapping still has a valid session.

    Its id is a UUID, which is not a `users.id`. The request must end here
    rather than at a `::bigint` cast somewhere inside an unrelated endpoint.
    """
    async with AsyncSession(bind=seeded) as session:
        with pytest.raises(IdentityMappingError):
            await tenant_from_supertokens_session(session, "d7c3f1e2-9a4b-4c8d-8e1f-2b3a4c5d6e7f")


async def test_no_context_is_not_the_same_as_no_access(seeded):
    """Why the bridge must fail closed, demonstrated rather than asserted.

    This is what a request would see if an unmappable session were allowed
    through with no context established. It is not an error and it is not a
    denial — under `user_id = NULLIF('', '')::bigint` every row simply compares
    NULL, and the endpoint returns an empty, entirely plausible result. A bug
    shaped like this would not announce itself.
    """
    async with AsyncSession(bind=seeded) as session:
        assert await _preset_names(session) == []
