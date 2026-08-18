"""add optimization_runs

Revision ID: 1289dae1f203
Revises: 0178c9d0e1f2
Create Date: 2026-08-18 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "1289dae1f203"
down_revision: str | None = "0178c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "optimization_runs"

# Repeated from 20260814_0019 rather than imported. That revision enumerated the
# user_id tables that existed *when it ran*, so a table added afterwards gets no
# policy from it and would be readable across tenants. Every new user-scoped
# table has to enable RLS itself, and a migration must keep working even if the
# helper it borrowed from is later edited.
_SYSTEM_CAPABILITIES = (
    "alert_checker",
    "alert_outbox",
    "performance_backfill",
    "position_monitor",
    "maintenance_cleanup",
    "startup_seed",
    "startup_cleanup",
    "cron_bootstrap",
    "alert_recovery",
)


def _tenant_predicate() -> str:
    system_values = ", ".join(f"'{value}'" for value in _SYSTEM_CAPABILITIES)
    return " OR ".join(
        [
            "current_setting('app.context_kind', true) = 'admin'",
            (
                "(current_setting('app.context_kind', true) = 'system' "
                f"AND current_setting('app.background_capability', true) IN ({system_values}))"
            ),
            (
                "(current_setting('app.context_kind', true) = 'tenant' "
                "AND user_id = NULLIF(current_setting('app.user_id', true), '')::bigint)"
            ),
        ]
    )


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column("objective", sa.String(30), nullable=False),
        sa.Column("start_date", sa.String(20), nullable=False),
        sa.Column("end_date", sa.String(20), nullable=False),
        sa.Column("trials_requested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trials_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("best_params", sa.JSON(), nullable=True),
        sa.Column("best_value", sa.Float(), nullable=True),
        sa.Column("best_metrics", sa.JSON(), nullable=True),
        sa.Column("baseline_params", sa.JSON(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("baseline_metrics", sa.JSON(), nullable=True),
        sa.Column("trials", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_optimization_runs_user_id", _TABLE, ["user_id"])
    op.create_index("ix_optimization_runs_ticker", _TABLE, ["ticker"])
    op.create_index("ix_optimization_runs_status", _TABLE, ["status"])
    op.create_index("ix_optimization_runs_created_at", _TABLE, ["created_at"])
    op.create_index("ix_optimization_runs_user_created", _TABLE, ["user_id", "created_at"])
    op.create_index("ix_optimization_runs_user_ticker", _TABLE, ["user_id", "ticker"])

    if op.get_bind().dialect.name != "postgresql":
        return

    policy = f"tenant_isolation_{_TABLE}"
    predicate = _tenant_predicate()
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{_TABLE}"')
    op.execute(f'CREATE POLICY "{policy}" ON "{_TABLE}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "tenant_isolation_{_TABLE}" ON "{_TABLE}"')
    op.drop_table(_TABLE)
