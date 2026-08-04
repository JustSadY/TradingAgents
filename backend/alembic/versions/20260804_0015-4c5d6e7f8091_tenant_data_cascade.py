"""cascade tenant-owned operational data on user deletion

Revision ID: 4c5d6e7f8091
Revises: 3b4c5d6e7f80
"""
from collections.abc import Sequence

from alembic import op

revision: str = "4c5d6e7f8091"
down_revision: str | None = "3b4c5d6e7f80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    ("portfolios", "portfolios_user_id_fkey"),
    ("analysis_results", "analysis_results_user_id_fkey"),
    ("multi_ticker_analyses", "multi_ticker_analyses_user_id_fkey"),
    ("price_alerts", "price_alerts_user_id_fkey"),
    ("webhook_deliveries", "webhook_deliveries_user_id_fkey"),
)


def _replace(table: str, constraint: str, ondelete: str) -> None:
    op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    op.create_foreign_key(
        constraint,
        table,
        "users",
        ["user_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    for table, constraint in _TABLES:
        _replace(table, constraint, "CASCADE")


def downgrade() -> None:
    for table, constraint in _TABLES:
        _replace(table, constraint, "SET NULL")
