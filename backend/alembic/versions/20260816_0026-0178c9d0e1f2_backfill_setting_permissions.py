"""Backfill current setting permissions for existing users.

Revision ID: 0178c9d0e1f2
Revises: f067b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0178c9d0e1f2"
down_revision: str | None = "f067b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTING_KEYS = (
    "general",
    "llm",
    "agents",
    "tools",
    "risk",
    "alerts",
    "webhooks",
    "cron",
    "presets",
    "memory",
    "personas",
)


def upgrade() -> None:
    values_sql = ", ".join(f"('{key}')" for key in _SETTING_KEYS)
    op.get_bind().execute(
        sa.text(
            "INSERT INTO user_setting_permissions (user_id, setting_key, allowed) "
            "SELECT users.id, setting_keys.setting_key, TRUE "
            "FROM users "
            f"CROSS JOIN (VALUES {values_sql}) AS setting_keys(setting_key) "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM user_setting_permissions AS existing "
            "WHERE existing.user_id = users.id "
            "AND existing.setting_key = setting_keys.setting_key"
            ")"
        )
    )


def downgrade() -> None:
    # This is a data backfill. Rows may have been edited by an administrator
    # after upgrade, so deleting them on downgrade would destroy current policy.
    pass
