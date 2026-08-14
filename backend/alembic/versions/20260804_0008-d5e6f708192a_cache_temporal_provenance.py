"""add temporal provenance to analyst report caches

Revision ID: d5e6f708192a
Revises: c4d5e6f70819
Create Date: 2026-08-04 08:20:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f708192a"
down_revision: str | None = "c4d5e6f70819"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    for table in ("news_analysis_cache", "analyst_report_cache"):
        if not _has_column(table, "trade_date"):
            op.add_column(table, sa.Column("trade_date", sa.String(length=10), nullable=True))
            op.create_index(f"ix_{table}_trade_date", table, ["trade_date"], unique=False)
        if not _has_column(table, "temporal_mode"):
            op.add_column(
                table,
                sa.Column("temporal_mode", sa.String(length=20), nullable=False, server_default="live"),
            )
            op.create_index(f"ix_{table}_temporal_mode", table, ["temporal_mode"], unique=False)
            op.alter_column(table, "temporal_mode", server_default=None)


def downgrade() -> None:
    for table in ("analyst_report_cache", "news_analysis_cache"):
        if _has_column(table, "temporal_mode"):
            op.drop_index(f"ix_{table}_temporal_mode", table_name=table)
            op.drop_column(table, "temporal_mode")
        if _has_column(table, "trade_date"):
            op.drop_index(f"ix_{table}_trade_date", table_name=table)
            op.drop_column(table, "trade_date")
