"""add analysis lease heartbeat
Revision ID: 2a3b4c5d6e7f
Revises: 192a3b4c5d6e
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: str | None = "192a3b4c5d6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analysis_results", sa.Column("worker_id", sa.String(100), nullable=True))
    op.create_index("ix_analysis_results_heartbeat_at", "analysis_results", ["heartbeat_at"])

def downgrade() -> None:
    op.drop_index("ix_analysis_results_heartbeat_at", table_name="analysis_results")
    op.drop_column("analysis_results", "worker_id")
    op.drop_column("analysis_results", "heartbeat_at")
