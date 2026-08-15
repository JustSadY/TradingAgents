"""add explicit request/background/refresh/share RLS contexts

Revision ID: 8a90b2c3d4e5
Revises: 7f8091a2b3c4
Create Date: 2026-08-14 18:20:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8a90b2c3d4e5"
down_revision: str | None = "7f8091a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def _base_predicate(table_name: str) -> str:
    system_values = ", ".join(f"'{value}'" for value in _SYSTEM_CAPABILITIES)
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


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        """
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
    ).fetchall()
    for schema_name, table_name in rows:
        policy_name = f"tenant_isolation_{table_name}"
        predicate = _base_predicate(table_name)
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{schema_name}"."{table_name}"')
        op.execute(f'ALTER TABLE "{schema_name}"."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{schema_name}"."{table_name}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        """
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
    ).fetchall()
    legacy = (
        "current_setting('app.is_admin', true) = 'true' OR "
        "user_id = NULLIF(current_setting('app.user_id', true), '')::bigint"
    )
    for schema_name, table_name in rows:
        policy_name = f"tenant_isolation_{table_name}"
        op.execute(f'DROP POLICY IF EXISTS "{policy_name}" ON "{schema_name}"."{table_name}"')
        op.execute(
            f'CREATE POLICY "{policy_name}" ON "{schema_name}"."{table_name}" '
            f"USING ({legacy}) WITH CHECK ({legacy})"
        )
