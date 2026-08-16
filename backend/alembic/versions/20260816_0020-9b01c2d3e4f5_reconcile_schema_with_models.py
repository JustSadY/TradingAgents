"""reconcile the migrated schema with the ORM models

Revision ID: 9b01c2d3e4f5
Revises: 8a90b2c3d4e5
Create Date: 2026-08-16 01:10:00.000000+00:00

`alembic check` against a freshly migrated database reported three groups of
differences from `Base.metadata`. None of them were visible in the test suite,
which runs on SQLite built by `create_all` straight from the models — so the
tests exercised a schema no deployment has ever had.

1. Seven foreign keys to `users` were left at NO ACTION where the models
   declare `ondelete="CASCADE"`. Revision 4c5d6e7f8091 gave the other nineteen
   tenant-owned tables their cascade and missed these. `delete_user_and_emit`
   clears six child tables by hand, none of which are these, so deleting any
   user who had ever saved settings, a preset, or agent/tool access failed on
   PostgreSQL with a foreign key violation while passing under SQLite.

2. Thirteen indexes the models declare were never created. Every one of them
   backs a user-scoped lookup, so those queries have been sequential scans in
   production and index scans in development.

3. `config_presets` was missing its `(user_id, name)` unique constraint, so
   production accepted duplicate preset names that development rejects.

`memory_vectors` also shows up in `alembic check` as a table to drop. It is
not an ORM model on purpose — revision 7f8091a2b3c4 owns it, the same way
LangGraph owns its checkpoint tables — so it is deliberately left alone.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9b01c2d3e4f5"
down_revision: str | None = "8a90b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, constraint name) for the foreign keys that should cascade from users.
_CASCADE_FKS: tuple[tuple[str, str], ...] = (
    ("agent_settings", "agent_settings_user_id_fkey"),
    ("agent_tool_settings", "agent_tool_settings_user_id_fkey"),
    ("app_settings", "app_settings_user_id_fkey"),
    ("config_presets", "config_presets_user_id_fkey"),
    ("user_agent_access", "user_agent_access_user_id_fkey"),
    ("user_tool_access", "user_tool_access_user_id_fkey"),
    ("user_tool_field_access", "user_tool_field_access_user_id_fkey"),
)

# (index name, table, columns) exactly as the models declare them.
_MISSING_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_asset_strategies_effective_at", "asset_strategies", ("effective_at",)),
    ("ix_asset_strategies_recorded_at", "asset_strategies", ("recorded_at",)),
    ("ix_assistant_messages_created_at", "assistant_messages", ("created_at",)),
    ("ix_assistant_messages_user_created", "assistant_messages", ("user_id", "created_at")),
    ("ix_config_presets_created_at", "config_presets", ("created_at",)),
    ("ix_multi_ticker_analyses_user_created", "multi_ticker_analyses", ("user_id", "created_at")),
    ("ix_multi_ticker_analyses_user_trade_date", "multi_ticker_analyses", ("user_id", "trade_date")),
    ("ix_price_alerts_user_enabled", "price_alerts", ("user_id", "enabled")),
    ("ix_price_alerts_user_ticker", "price_alerts", ("user_id", "ticker")),
    ("ix_shared_reports_created_at", "shared_reports", ("created_at",)),
    ("ix_shared_reports_expires_at", "shared_reports", ("expires_at",)),
    ("ix_shared_reports_user_id", "shared_reports", ("user_id",)),
    ("ix_webhook_deliveries_user_created", "webhook_deliveries", ("user_id", "created_at")),
)

_PRESET_UNIQUE = "uq_config_preset_user_name"


def upgrade() -> None:
    for table, constraint in _CASCADE_FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "users", ["user_id"], ["id"], ondelete="CASCADE")

    for name, table, columns in _MISSING_INDEXES:
        op.create_index(name, table, list(columns), if_not_exists=True)

    # Existing rows may already violate the constraint the models assume, and
    # failing the deployment over a duplicate preset name would be worse than
    # keeping one of them. Collapse duplicates onto the oldest row first.
    op.execute(
        """
        DELETE FROM config_presets a
        USING config_presets b
        WHERE a.user_id IS NOT DISTINCT FROM b.user_id
          AND a.name = b.name
          AND a.id > b.id
        """
    )
    op.create_unique_constraint(_PRESET_UNIQUE, "config_presets", ["user_id", "name"])


def downgrade() -> None:
    op.drop_constraint(_PRESET_UNIQUE, "config_presets", type_="unique")

    for name, table, _columns in _MISSING_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)

    for table, constraint in _CASCADE_FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "users", ["user_id"], ["id"])
