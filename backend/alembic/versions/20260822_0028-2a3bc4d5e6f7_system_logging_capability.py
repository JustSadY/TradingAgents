"""allow the system_logging background capability through tenant RLS

Revision ID: 2a3bc4d5e6f7
Revises: 1289dae1f203
Create Date: 2026-08-22 00:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2a3bc4d5e6f7"
down_revision: str | None = "1289dae1f203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The database log writer runs off-request and persists records that belong to
# no tenant at all (``system_logs.user_id IS NULL``). Under the policy created
# by 20260814_0019 no available context could satisfy the WITH CHECK for such a
# row, so every flush failed with InsufficientPrivilegeError and the System Logs
# page stayed permanently empty on PostgreSQL. Adding the capability to the
# audited allowlist is what lets that one writer through.
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
    "system_logging",
)

_LEGACY_SYSTEM_CAPABILITIES = tuple(
    value for value in _SYSTEM_CAPABILITIES if value != "system_logging"
)

_USER_ID_TABLES = """
    SELECT DISTINCT c.table_schema, c.table_name
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema
     AND t.table_name = c.table_name
    WHERE c.table_schema = current_schema()
      AND c.column_name = 'user_id'
      AND t.table_type = 'BASE TABLE'
      AND c.table_name <> 'alembic_version'
    ORDER BY c.table_name
"""


def _base_predicate(table_name: str, capabilities: Sequence[str]) -> str:
    system_values = ", ".join(f"'{value}'" for value in capabilities)
    clauses = [
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
    if table_name == "refresh_sessions":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'refresh' AND ("
            "id = NULLIF(current_setting('app.refresh_session_id', true), '') "
            "OR user_id = NULLIF(current_setting('app.user_id', true), '')::bigint))"
        )
    elif table_name == "shared_reports":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'share' "
            "AND token = NULLIF(current_setting('app.public_share_token', true), ''))"
        )
    elif table_name == "analysis_results":
        clauses.append(
            "(current_setting('app.context_kind', true) = 'share' "
            "AND id = NULLIF(current_setting('app.share_analysis_id', true), '')::bigint)"
        )
    return " OR ".join(clauses)


def _rewrite_policies(capabilities: Sequence[str]) -> None:
    bind = op.get_bind()
    for schema_name, table_name in bind.exec_driver_sql(_USER_ID_TABLES).fetchall():
        policy_name = f"tenant_isolation_{table_name}"
        predicate = _base_predicate(table_name, capabilities)
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{schema_name}"."{table_name}"')
        op.execute(f'ALTER TABLE "{schema_name}"."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{schema_name}"."{table_name}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def upgrade() -> None:
    _rewrite_policies(_SYSTEM_CAPABILITIES)


def downgrade() -> None:
    _rewrite_policies(_LEGACY_SYSTEM_CAPABILITIES)
