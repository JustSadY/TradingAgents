"""make report shares single-row, revocable, and rotatable

Revision ID: f708192a3b4c
Revises: e6f708192a3b
Create Date: 2026-08-04 08:50:00+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f708192a3b4c"
down_revision: str | None = "e6f708192a3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("shared_reports", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_shared_reports_revoked_at", "shared_reports", ["revoked_at"])
    # Preserve the newest row before enforcing one share lifecycle per owner/report.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DELETE FROM shared_reports a USING shared_reports b "
            "WHERE a.user_id=b.user_id AND a.analysis_id=b.analysis_id "
            "AND (a.created_at < b.created_at OR (a.created_at=b.created_at AND a.id < b.id))"
        )
    else:
        op.execute(
            "DELETE FROM shared_reports WHERE id NOT IN "
            "(SELECT MAX(id) FROM shared_reports GROUP BY user_id, analysis_id)"
        )
    op.create_unique_constraint(
        "uq_shared_reports_user_analysis", "shared_reports", ["user_id", "analysis_id"]
    )

def downgrade() -> None:
    op.drop_constraint("uq_shared_reports_user_analysis", "shared_reports", type_="unique")
    op.drop_index("ix_shared_reports_revoked_at", table_name="shared_reports")
    op.drop_column("shared_reports", "revoked_at")
