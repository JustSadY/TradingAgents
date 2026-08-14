"""add transactional alert outbox
Revision ID: 3b4c5d6e7f80
Revises: 2a3b4c5d6e7f
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3b4c5d6e7f80"
down_revision: str | None = "2a3b4c5d6e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "alert_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("price_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("current_value", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_outbox_status_created", "alert_outbox", ["status", "created_at"])
    op.create_index("ix_alert_outbox_alert_id", "alert_outbox", ["alert_id"])
    op.create_index("ix_alert_outbox_user_id", "alert_outbox", ["user_id"])

def downgrade() -> None:
    op.drop_table("alert_outbox")
