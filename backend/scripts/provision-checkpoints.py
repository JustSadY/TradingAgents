#!/usr/bin/env python
"""Create LangGraph's checkpoint tables with a role that is allowed to.

LangGraph owns its checkpoint schema and creates it through ``setup()``, which
needs CREATE on the schema. A hardened deployment connects the application with
a non-owner, NOBYPASSRLS role that deliberately has no such privilege, so the
app cannot bootstrap those tables itself — every analysis fails with
``permission denied for schema public`` (or, once the tables are half-created,
``relation "checkpoints" does not exist``).

This runs the same idempotent ``setup()`` with the migration credential, so the
tables are owned by the migrator and the runtime role picks up DML through the
default privileges ``deploy/provision-postgres-roles.sh`` grants it.

Run it after ``alembic upgrade head``, and again after a LangGraph upgrade that
adds a checkpoint migration. ``deploy/install.sh`` and ``deploy/update.sh`` do
both automatically.

Usage:
    MIGRATION_DATABASE_URL=postgresql+asyncpg://owner:pw@host:5432/db \
        python backend/scripts/provision-checkpoints.py

Falls back to DATABASE_URL when MIGRATION_DATABASE_URL is unset, which is what
a single-role development database wants.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))


def _resolve_dsn() -> str:
    """Return a psycopg DSN, preferring the migration credential."""
    url = (os.environ.get("MIGRATION_DATABASE_URL") or "").strip()
    if not url:
        # Import only when needed: with MIGRATION_DATABASE_URL set this script
        # must not require the application's full settings to be loadable.
        from backend.core.config import get_settings

        url = (get_settings().DATABASE_URL or "").strip()

    scheme, sep, rest = url.partition("://")
    if not sep or not scheme.lower().startswith("postgres"):
        raise SystemExit(
            "LangGraph checkpoints require PostgreSQL. "
            f"Set MIGRATION_DATABASE_URL (or DATABASE_URL) to a PostgreSQL URL; got: {scheme or url!r}"
        )
    # SQLAlchemy driver suffixes (+asyncpg, +psycopg) are not psycopg DSNs.
    return f"postgresql://{rest}"


def main() -> int:
    dsn = _resolve_dsn()
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()

    import psycopg

    with psycopg.connect(dsn) as conn:
        present = conn.execute("SELECT to_regclass('public.checkpoints')").fetchone()
    if not (present and present[0]):
        print("setup() reported success but public.checkpoints is still absent.", file=sys.stderr)
        return 1

    print("LangGraph checkpoint tables are provisioned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
