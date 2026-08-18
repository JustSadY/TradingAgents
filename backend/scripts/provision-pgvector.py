#!/usr/bin/env python
"""Make the pgvector extension usable before Alembic needs it.

Revision ``20260814_0018`` refuses to run unless ``vector`` is installed and
then creates ``memory_vectors.embedding vector``. For a locally managed
database ``deploy/provision-postgres-roles.sh`` runs ``CREATE EXTENSION IF NOT
EXISTS vector`` — but ``SKIP_DB=1`` (external or managed PostgreSQL) skips that
script entirely, so the first sign of trouble was a raw traceback in the middle
of the migration run.

This creates the extension when the migration credential is allowed to, and
otherwise stops with the SQL an operator has to run themselves. It also catches
the managed-provider variant of the same failure: Supabase installs extensions
into an ``extensions`` schema, so ``vector`` can be installed and still leave
``type "vector" does not exist`` two statements later.

Usage:
    MIGRATION_DATABASE_URL=postgresql+asyncpg://owner:pw@host:5432/db \
        python backend/scripts/provision-pgvector.py

Falls back to DATABASE_URL when MIGRATION_DATABASE_URL is unset.
"""

from __future__ import annotations

import sys

from _pg_dsn import resolve_migration_dsn

CANNOT_CREATE = """\
Install pgvector on the database yourself, then re-run this step.

  Managed PostgreSQL (Supabase, RDS, Cloud SQL): enable the "vector" extension
  from the provider's extensions UI, or run as an administrative role:

      CREATE EXTENSION IF NOT EXISTS vector;

  Self-managed PostgreSQL: install the server package first
  (e.g. postgresql-17-pgvector), then run the same statement as a superuser."""


def _search_path_fix(schema: str) -> str:
    return f"""\
The pgvector extension is installed in schema "{schema}", which is not on the
search_path of the role this step connects with, so the "vector" type cannot be
resolved and the migration would fail with: type "vector" does not exist.

Fix it one of these two ways, then re-run this step.

  Put the extension's schema on the search_path of BOTH database roles — the
  migration role and the runtime role from DATABASE_URL:

      ALTER ROLE "<migration_role>" SET search_path = public, {schema};
      ALTER ROLE "<runtime_role>"   SET search_path = public, {schema};

  Or move the extension into public, if nothing else on this database depends
  on it living in "{schema}":

      ALTER EXTENSION vector SET SCHEMA public;"""


def vector_type_resolves(conn) -> bool:
    """True when the connecting role can name the ``vector`` type unqualified."""
    row = conn.execute("SELECT to_regtype('vector')").fetchone()
    return bool(row and row[0])


def installed_schema(conn) -> str | None:
    """Schema the extension is installed into, or None when it is absent."""
    row = conn.execute(
        "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
    ).fetchone()
    return row[0] if row else None


def ensure_vector(conn) -> tuple[int, str]:
    """Return (exit code, message) for a connection to the target database."""
    if vector_type_resolves(conn):
        return 0, "pgvector is installed and the 'vector' type resolves."

    schema = installed_schema(conn)
    if schema is None:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception as exc:  # psycopg raises a driver-specific error here
            return 1, f"pgvector is not installed and this role cannot create it: {exc}\n\n{CANNOT_CREATE}"
        schema = installed_schema(conn)

    if not vector_type_resolves(conn):
        return 1, _search_path_fix(schema or "extensions")
    return 0, f"pgvector is available (extension schema: {schema})."


def main() -> int:
    dsn = resolve_migration_dsn()
    import psycopg

    # Autocommit so a denied CREATE EXTENSION does not abort the transaction
    # the follow-up probes need.
    with psycopg.connect(dsn, autocommit=True) as conn:
        code, message = ensure_vector(conn)

    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
