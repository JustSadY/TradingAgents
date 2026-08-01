"""make AI signal execution an explicit per-user opt-in

Revision ID: c4d5e6f70819
Revises: b3c4d5e6f708
Create Date: 2026-08-01 13:30:00.000000+00:00

Directional analysis is informational by default.  Persist a separate account
setting so an analysis cannot silently become an order simply because it
finished with Buy, Overweight, Sell, or Underweight.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f70819"
down_revision: str | None = "b3c4d5e6f708"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    if _has_column("app_settings", "auto_execute_signals"):
        return
    op.add_column(
        "app_settings",
        sa.Column("auto_execute_signals", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("app_settings", "auto_execute_signals", server_default=None)


def downgrade() -> None:
    if _has_column("app_settings", "auto_execute_signals"):
        op.drop_column("app_settings", "auto_execute_signals")
