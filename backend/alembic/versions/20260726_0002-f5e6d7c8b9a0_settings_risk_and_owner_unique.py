"""settings risk controls and single-owner invariant

Revision ID: f5e6d7c8b9a0
Revises: c1a2b3c4d5e6
Create Date: 2026-07-26 00:02:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5e6d7c8b9a0"
down_revision: str | None = "c1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    # SQL-generation mode intentionally has no live connection to inspect.
    # This revision follows a baseline that lacks all three columns, so emit
    # the ADD COLUMN statements in that mode; online upgrades retain the
    # idempotent inspection needed for legacy databases.
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("app_settings", "allow_short_selling"):
        op.add_column(
            "app_settings",
            sa.Column("allow_short_selling", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.alter_column("app_settings", "allow_short_selling", server_default=None)
    if not _has_column("app_settings", "max_concentration_pct"):
        op.add_column(
            "app_settings",
            sa.Column("max_concentration_pct", sa.Float(), nullable=False, server_default=sa.text("25.0")),
        )
        op.alter_column("app_settings", "max_concentration_pct", server_default=None)
    if not _has_column("app_settings", "max_gross_exposure"):
        op.add_column(
            "app_settings",
            sa.Column("max_gross_exposure", sa.Float(), nullable=False, server_default=sa.text("3.0")),
        )
        op.alter_column("app_settings", "max_gross_exposure", server_default=None)

    # Previous unrestricted preset writes could create duplicate rows for a
    # user. Keep the most recently updated state before enforcing the DB-level
    # one-owner invariant; a migration must be able to repair such installs
    # rather than fail halfway through an upgrade.
    op.execute(
        """
        DELETE FROM app_settings
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY COALESCE(user_id, 0)
                           ORDER BY updated_at DESC NULLS LAST, id DESC
                       ) AS row_num
                FROM app_settings
            ) duplicates
            WHERE row_num > 1
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_app_settings_owner ON app_settings (COALESCE(user_id, 0))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_app_settings_owner")
    for column in ("max_gross_exposure", "max_concentration_pct", "allow_short_selling"):
        if _has_column("app_settings", column):
            op.drop_column("app_settings", column)
