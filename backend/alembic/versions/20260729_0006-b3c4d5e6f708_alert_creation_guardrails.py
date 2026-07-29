"""add user-configurable alert creation guardrails

Revision ID: b3c4d5e6f708
Revises: a2b3c4d5e6f7
Create Date: 2026-07-29 10:20:00.000000+00:00

AI chart annotations previously persisted every extracted support/resistance
level.  Store bounded per-user policy on ``app_settings`` and enough origin
metadata on each alert to enforce a cap per analysis run plus a cooldown for
equivalent AI alerts.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3c4d5e6f708"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def _add_required_int(column: str, default: int) -> None:
    if _has_column("app_settings", column):
        return
    op.add_column(
        "app_settings",
        sa.Column(column, sa.Integer(), nullable=False, server_default=sa.text(str(default))),
    )
    op.alter_column("app_settings", column, server_default=None)


def upgrade() -> None:
    _add_required_int("max_active_alerts", 30)
    _add_required_int("max_ai_alerts_per_run", 3)
    _add_required_int("ai_alert_cooldown_hours", 24)

    if not _has_column("price_alerts", "creation_source"):
        op.add_column(
            "price_alerts",
            sa.Column(
                "creation_source",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'manual'"),
            ),
        )
        # Existing rows are intentionally classified as manual: their origin
        # was not recorded and guessing would unexpectedly suppress them.
        op.alter_column("price_alerts", "creation_source", server_default=None)
    if not _has_column("price_alerts", "creation_run_id"):
        op.add_column("price_alerts", sa.Column("creation_run_id", sa.String(length=100), nullable=True))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_alerts_user_source_run "
        "ON price_alerts (user_id, creation_source, creation_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_alerts_ai_equivalence "
        "ON price_alerts (user_id, creation_source, ticker, condition, alert_type, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_price_alerts_ai_equivalence")
    op.execute("DROP INDEX IF EXISTS ix_price_alerts_user_source_run")
    for column in ("creation_run_id", "creation_source"):
        if _has_column("price_alerts", column):
            op.drop_column("price_alerts", column)
    for column in ("ai_alert_cooldown_hours", "max_ai_alerts_per_run", "max_active_alerts"):
        if _has_column("app_settings", column):
            op.drop_column("app_settings", column)
