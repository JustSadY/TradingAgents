"""add assistant pending-action confirmations

Revision ID: e6f708192a3b
Revises: d5e6f708192a
Create Date: 2026-08-04 08:35:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e6f708192a3b"
down_revision: str | None = "d5e6f708192a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "assistant_pending_actions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_pending_actions_user_id", "assistant_pending_actions", ["user_id"])
    op.create_index(
        "ix_assistant_pending_actions_user_created",
        "assistant_pending_actions", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_assistant_pending_actions_expiry",
        "assistant_pending_actions", ["expires_at", "consumed_at"]
    )

def downgrade() -> None:
    op.drop_index("ix_assistant_pending_actions_expiry", table_name="assistant_pending_actions")
    op.drop_index("ix_assistant_pending_actions_user_created", table_name="assistant_pending_actions")
    op.drop_index("ix_assistant_pending_actions_user_id", table_name="assistant_pending_actions")
    op.drop_table("assistant_pending_actions")
