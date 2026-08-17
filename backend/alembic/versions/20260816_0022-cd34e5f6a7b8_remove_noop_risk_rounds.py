"""remove the retired no-op risk round setting

Revision ID: cd34e5f6a7b8
Revises: bc23d4e5f6a7
Create Date: 2026-08-16 13:55:00.000000+00:00

The current Risk Debate node performs one merged LLM call and never consumes
max_risk_rounds. The setting was persisted and editable despite having no
runtime effect, so remove the misleading contract and its database column.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cd34e5f6a7b8"
down_revision: str | None = "bc23d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("app_settings", "max_risk_rounds")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("max_risk_rounds", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
