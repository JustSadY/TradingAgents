"""Shared DSN resolution for the deployment provisioning scripts.

Both provisioning scripts run outside the application process, with the
migration credential rather than the runtime one, and both need a psycopg DSN
rather than a SQLAlchemy URL. Keeping the rule in one place stops the two from
disagreeing about which credential wins.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def resolve_migration_dsn() -> str:
    """Return a psycopg DSN, preferring the migration credential.

    Falls back to DATABASE_URL when MIGRATION_DATABASE_URL is unset, which is
    what a single-role development database wants.
    """
    url = (os.environ.get("MIGRATION_DATABASE_URL") or "").strip()
    if not url:
        # Import only when needed: with MIGRATION_DATABASE_URL set these
        # scripts must not require the application's full settings to load.
        from backend.core.config import get_settings

        url = (get_settings().DATABASE_URL or "").strip()

    scheme, sep, rest = url.partition("://")
    if not sep or not scheme.lower().startswith("postgres"):
        raise SystemExit(
            "This deployment step requires PostgreSQL. "
            f"Set MIGRATION_DATABASE_URL (or DATABASE_URL) to a PostgreSQL URL; got: {scheme or url!r}"
        )
    # SQLAlchemy driver suffixes (+asyncpg, +psycopg) are not psycopg DSNs.
    return f"postgresql://{rest}"
