"""add trading accounting and broker audit fields
Revision ID: 192a3b4c5d6e
Revises: 08192a3b4c5d
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
revision: str = "192a3b4c5d6e"
down_revision: str | None = "08192a3b4c5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("holdings", sa.Column("interest_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("financing_cost", sa.Numeric(20, 8), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("external_order_id", sa.String(100), nullable=True))
    op.create_index("ix_orders_external_order_id", "orders", ["external_order_id"])

def downgrade() -> None:
    op.drop_index("ix_orders_external_order_id", table_name="orders")
    op.drop_column("orders", "external_order_id")
    op.drop_column("orders", "financing_cost")
    op.drop_column("holdings", "interest_updated_at")
