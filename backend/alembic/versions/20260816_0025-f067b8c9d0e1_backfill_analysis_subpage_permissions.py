"""Backfill permissions for analysis subpages introduced after analysis access.

Revision ID: f067b8c9d0e1
Revises: ef56a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f067b8c9d0e1"
down_revision: str | None = "ef56a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO user_page_permissions (user_id, page_key, allowed) "
            "SELECT analysis_perm.user_id, page_keys.page_key, TRUE "
            "FROM user_page_permissions AS analysis_perm "
            "CROSS JOIN (VALUES ('screener'), ('sector-rotation'), ('earnings')) AS page_keys(page_key) "
            "WHERE analysis_perm.page_key = 'analysis' AND analysis_perm.allowed = TRUE "
            "AND NOT EXISTS ("
            "SELECT 1 FROM user_page_permissions AS existing "
            "WHERE existing.user_id = analysis_perm.user_id "
            "AND existing.page_key = page_keys.page_key"
            ")"
        )
    )


def downgrade() -> None:
    # This is a data backfill. Rows may have been edited by an administrator
    # after upgrade, so deleting them on downgrade would destroy current policy.
    pass
