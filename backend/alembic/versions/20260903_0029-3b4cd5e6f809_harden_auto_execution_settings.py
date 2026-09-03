"""harden automatic execution safety settings

Revision ID: 3b4cd5e6f809
Revises: 2a3bc4d5e6f7
Create Date: 2026-09-03 19:30:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "3b4cd5e6f809"
down_revision = "2a3bc4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing users may have opted into automatic signal execution before the
    # stability controller and quality gate became mandatory companions.  Bring
    # those rows onto the same invariant enforced by settings_service.
    op.execute(
        sa.text(
            """
            UPDATE app_settings
               SET quality_gate_enabled = TRUE,
                   decision_stability_mode = 'enforce'
             WHERE auto_execute_signals = TRUE
               AND (
                    quality_gate_enabled IS DISTINCT FROM TRUE
                    OR decision_stability_mode IS DISTINCT FROM 'enforce'
               )
            """
        )
    )


def downgrade() -> None:
    # Safety backfills are intentionally not reversed: there is no reliable way
    # to distinguish a value that predated this migration from one deliberately
    # chosen after it.
    pass
