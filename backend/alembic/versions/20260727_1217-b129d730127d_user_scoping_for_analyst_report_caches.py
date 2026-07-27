"""user scoping for analyst report caches

The ``AnalystReportCache`` / ``NewsAnalysisCache`` models
(``backend/models/news_cache.py``) carry ``user_id`` and
``config_fingerprint`` columns that the baseline migration never created —
those columns were added to the models after the baseline was generated, with
no follow-up migration. On SQLite (dev/test) this was invisible because
``create_all_tables()`` runs ``Base.metadata.create_all`` there, which builds
tables straight from the current models. Any fresh PostgreSQL database goes
through Alembic exclusively, so every query built from the current
``AnalystReportCache``/``NewsAnalysisCache`` models (i.e. every analyst cache
lookup) fails with ``UndefinedColumnError``.

Revision ID: b129d730127d
Revises: f5e6d7c8b9a0
Create Date: 2026-07-27 12:17:05.160295+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b129d730127d"
down_revision: str | None = "f5e6d7c8b9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("analyst_report_cache", "news_analysis_cache")


def _has_column(table: str, column: str) -> bool:
    # SQL-generation mode has no live connection to inspect; both tables
    # predate this revision and neither column exists yet, so the offline
    # (--sql) path can assume "missing" unconditionally.
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    for table in _TABLES:
        if not _has_column(table, "user_id"):
            op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                f"{table}_user_id_fkey",
                table,
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if not _has_column(table, "config_fingerprint"):
            op.add_column(table, sa.Column("config_fingerprint", sa.String(length=64), nullable=True))
        op.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_user_id" ON "{table}" ("user_id")')
        op.execute(f'CREATE INDEX IF NOT EXISTS "ix_{table}_config_fingerprint" ON "{table}" ("config_fingerprint")')

    # Matches AnalystReportCache.__table_args__: the composite index the
    # cache-lookup query (analyst_cache.py::check_analyst_cache) filters on.
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_analyst_report_cache_lookup" '
        'ON "analyst_report_cache" ("user_id", "analyst_key", "ticker", "data_hash")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "ix_analyst_report_cache_lookup"')
    for table in _TABLES:
        op.execute(f'DROP INDEX IF EXISTS "ix_{table}_config_fingerprint"')
        op.execute(f'DROP INDEX IF EXISTS "ix_{table}_user_id"')
        if _has_column(table, "config_fingerprint"):
            op.drop_column(table, "config_fingerprint")
        if _has_column(table, "user_id"):
            op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{table}_user_id_fkey"')
            op.drop_column(table, "user_id")
