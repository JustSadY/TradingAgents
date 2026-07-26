"""cascade_and_relationship_rules

Revision ID: c1a2b3c4d5e6
Revises: 89f1a049b357
Create Date: 2026-07-20 00:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1a2b3c4d5e6"
down_revision: str | None = "89f1a049b357"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_fk_if_exists(table: str, constraint: str) -> None:
    """Drop one known PostgreSQL FK in both online and ``--sql`` modes.

    The prior migration queried PostgreSQL's catalog to decide whether a
    constraint/index existed. Alembic's offline SQL generator has no result
    set for those queries, so ``alembic upgrade --sql`` crashed before it
    could produce a deployable script.  These identifiers are static migration
    data, therefore PostgreSQL's native ``IF EXISTS`` is both safe and works
    identically online and offline.
    """
    op.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')


def _create_index_if_missing(index: str, table: str, columns: list[str]) -> None:
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    op.execute(f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" ({quoted_columns})')


def _drop_index_if_exists(index: str) -> None:
    op.execute(f'DROP INDEX IF EXISTS "{index}"')


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Foreign-key cascade rules                                       #
    # ------------------------------------------------------------------ #

    # portfolios.user_id → users.id  (SET NULL)
    _drop_fk_if_exists("portfolios", "portfolios_user_id_fkey")
    op.create_foreign_key(
        "portfolios_user_id_fkey",
        "portfolios",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # holdings.portfolio_id → portfolios.id  (CASCADE)
    _drop_fk_if_exists("holdings", "holdings_portfolio_id_fkey")
    op.create_foreign_key(
        "holdings_portfolio_id_fkey",
        "holdings",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # orders.portfolio_id → portfolios.id  (CASCADE)
    _drop_fk_if_exists("orders", "orders_portfolio_id_fkey")
    op.create_foreign_key(
        "orders_portfolio_id_fkey",
        "orders",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # orders.analysis_id → analysis_results.id  (SET NULL)
    _drop_fk_if_exists("orders", "orders_analysis_id_fkey")
    op.create_foreign_key(
        "orders_analysis_id_fkey",
        "orders",
        "analysis_results",
        ["analysis_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # trade_notes.order_id → orders.id  (CASCADE)
    _drop_fk_if_exists("trade_notes", "trade_notes_order_id_fkey")
    op.create_foreign_key(
        "trade_notes_order_id_fkey",
        "trade_notes",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # trade_notes.user_id → users.id  (CASCADE)
    _drop_fk_if_exists("trade_notes", "trade_notes_user_id_fkey")
    op.create_foreign_key(
        "trade_notes_user_id_fkey",
        "trade_notes",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # shared_reports.user_id → users.id  (CASCADE)
    _drop_fk_if_exists("shared_reports", "shared_reports_user_id_fkey")
    op.create_foreign_key(
        "shared_reports_user_id_fkey",
        "shared_reports",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # shared_reports.analysis_id → analysis_results.id  (CASCADE)
    _drop_fk_if_exists("shared_reports", "shared_reports_analysis_id_fkey")
    op.create_foreign_key(
        "shared_reports_analysis_id_fkey",
        "shared_reports",
        "analysis_results",
        ["analysis_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # analysis_results.user_id → users.id  (SET NULL)
    _drop_fk_if_exists("analysis_results", "analysis_results_user_id_fkey")
    op.create_foreign_key(
        "analysis_results_user_id_fkey",
        "analysis_results",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # assistant_messages.user_id → users.id  (CASCADE)
    _drop_fk_if_exists("assistant_messages", "assistant_messages_user_id_fkey")
    op.create_foreign_key(
        "assistant_messages_user_id_fkey",
        "assistant_messages",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # user_page_permissions.user_id → users.id  (CASCADE)
    _drop_fk_if_exists("user_page_permissions", "user_page_permissions_user_id_fkey")
    op.create_foreign_key(
        "user_page_permissions_user_id_fkey",
        "user_page_permissions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # user_setting_permissions.user_id → users.id  (CASCADE)
    _drop_fk_if_exists("user_setting_permissions", "user_setting_permissions_user_id_fkey")
    op.create_foreign_key(
        "user_setting_permissions_user_id_fkey",
        "user_setting_permissions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ------------------------------------------------------------------ #
    # 2. New composite indexes                                           #
    # ------------------------------------------------------------------ #

    _create_index_if_missing("ix_holdings_portfolio_ticker", "holdings", ["portfolio_id", "ticker"])
    _create_index_if_missing("ix_orders_portfolio_ticker", "orders", ["portfolio_id", "ticker"])
    _create_index_if_missing("ix_analysis_results_user_ticker", "analysis_results", ["user_id", "ticker"])
    _create_index_if_missing("ix_analysis_results_trade_date", "analysis_results", ["trade_date"])
    _create_index_if_missing("ix_system_logs_user_created", "system_logs", ["user_id", "created_at"])
    _create_index_if_missing("ix_price_alerts_enabled_triggered", "price_alerts", ["enabled", "triggered_at"])
    _create_index_if_missing("ix_users_is_active", "users", ["is_active"])
    _create_index_if_missing("ix_market_daily_summaries_user_date", "market_daily_summaries", ["user_id", "date"])


def downgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Remove added indexes                                            #
    # ------------------------------------------------------------------ #

    for index_name in [
        "ix_market_daily_summaries_user_date",
        "ix_users_is_active",
        "ix_price_alerts_enabled_triggered",
        "ix_system_logs_user_created",
        "ix_analysis_results_trade_date",
        "ix_analysis_results_user_ticker",
        "ix_orders_portfolio_ticker",
        "ix_holdings_portfolio_ticker",
    ]:
        _drop_index_if_exists(index_name)

    # ------------------------------------------------------------------ #
    # 2. Restore original FK constraints (no ondelete)                   #
    # ------------------------------------------------------------------ #

    def _restore_fk(table, constraint, columns, ref_table, ref_columns):
        _drop_fk_if_exists(table, constraint)
        op.create_foreign_key(constraint, table, ref_table, columns, ref_columns)

    _restore_fk("portfolios", "portfolios_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("holdings", "holdings_portfolio_id_fkey", ["portfolio_id"], "portfolios", ["id"])
    _restore_fk("orders", "orders_portfolio_id_fkey", ["portfolio_id"], "portfolios", ["id"])
    _restore_fk("orders", "orders_analysis_id_fkey", ["analysis_id"], "analysis_results", ["id"])
    _restore_fk("trade_notes", "trade_notes_order_id_fkey", ["order_id"], "orders", ["id"])
    _restore_fk("trade_notes", "trade_notes_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("shared_reports", "shared_reports_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("shared_reports", "shared_reports_analysis_id_fkey", ["analysis_id"], "analysis_results", ["id"])
    _restore_fk("analysis_results", "analysis_results_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("assistant_messages", "assistant_messages_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("user_page_permissions", "user_page_permissions_user_id_fkey", ["user_id"], "users", ["id"])
    _restore_fk("user_setting_permissions", "user_setting_permissions_user_id_fkey", ["user_id"], "users", ["id"])
