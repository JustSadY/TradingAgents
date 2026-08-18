"""The pgvector preflight the installer runs before Alembic.

Revision 20260814_0018 raises when the extension is missing, and creates a
``vector`` column immediately after. A managed database reached through
``SKIP_DB=1`` never goes through ``provision-postgres-roles.sh``, so nothing
had created the extension and the failure surfaced as a raw traceback in the
middle of a migration run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "backend" / "scripts"


def _load(name: str):
    """Import a hyphenated script by path, with its siblings importable."""
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pgvector = _load("provision-pgvector")


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Answers only the three statements the preflight issues."""

    def __init__(
        self,
        *,
        resolves: bool = False,
        schema: str | None = None,
        create_error: Exception | None = None,
        creates_into: str | None = "public",
        create_resolves: bool = True,
    ):
        self.resolves = resolves
        self.schema = schema
        self.create_error = create_error
        self.creates_into = creates_into
        self.create_resolves = create_resolves
        self.statements: list[str] = []

    def execute(self, sql: str):
        self.statements.append(sql)
        if "to_regtype" in sql:
            return _Cursor(("vector",) if self.resolves else (None,))
        if "pg_extension" in sql:
            return _Cursor((self.schema,) if self.schema else None)
        if sql.startswith("CREATE EXTENSION"):
            if self.create_error is not None:
                raise self.create_error
            self.schema = self.creates_into
            self.resolves = self.create_resolves
            return _Cursor(None)
        raise AssertionError(f"unexpected statement: {sql}")


def test_an_already_usable_extension_is_left_alone():
    conn = _FakeConn(resolves=True, schema="public")

    code, message = pgvector.ensure_vector(conn)

    assert code == 0
    assert not any(s.startswith("CREATE EXTENSION") for s in conn.statements)
    assert "resolves" in message


def test_a_missing_extension_is_created_when_the_role_may():
    conn = _FakeConn()

    code, message = pgvector.ensure_vector(conn)

    assert code == 0
    assert any(s.startswith("CREATE EXTENSION") for s in conn.statements)
    assert "public" in message


def test_a_denied_create_reports_the_sql_an_operator_must_run():
    conn = _FakeConn(create_error=RuntimeError('permission denied to create extension "vector"'))

    code, message = pgvector.ensure_vector(conn)

    assert code == 1
    assert "permission denied to create extension" in message
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in message


def test_an_extension_off_the_search_path_is_a_failure_not_a_pass():
    """Supabase installs extensions into `extensions`, so `vector` is installed
    and the very next migration statement still fails to resolve the type."""
    conn = _FakeConn(resolves=False, schema="extensions")

    code, message = pgvector.ensure_vector(conn)

    assert code == 1
    assert not any(s.startswith("CREATE EXTENSION") for s in conn.statements)
    assert "extensions" in message
    assert "search_path" in message
    assert "ALTER EXTENSION vector SET SCHEMA public;" in message


def test_a_create_that_lands_off_the_search_path_is_also_caught():
    conn = _FakeConn(creates_into="extensions", create_resolves=False)

    code, message = pgvector.ensure_vector(conn)

    assert code == 1
    assert "search_path" in message


class TestDsnResolution:
    """Both provisioning scripts share this, so they cannot disagree."""

    def test_the_migration_credential_wins_and_the_driver_suffix_is_stripped(self, monkeypatch):
        dsn = _load("_pg_dsn")
        monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql+asyncpg://m:p@h:5432/db")
        assert dsn.resolve_migration_dsn() == "postgresql://m:p@h:5432/db"

    def test_a_non_postgres_url_is_refused(self, monkeypatch):
        dsn = _load("_pg_dsn")
        monkeypatch.setenv("MIGRATION_DATABASE_URL", "sqlite+aiosqlite:////tmp/x.db")
        with pytest.raises(SystemExit, match="requires PostgreSQL"):
            dsn.resolve_migration_dsn()
