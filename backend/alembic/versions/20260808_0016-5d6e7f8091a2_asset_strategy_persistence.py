"""add persistent asset strategy and immutable revision ledger

Revision ID: 5d6e7f8091a2
Revises: 4c5d6e7f8091
Create Date: 2026-08-08 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d6e7f8091a2"
down_revision: str | None = "4c5d6e7f8091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_strategies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("strategic_bias", sa.String(length=30), nullable=False, server_default="NEUTRAL"),
        sa.Column("conviction", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("accepted_rating", sa.String(length=30), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=False, server_default=""),
        sa.Column("key_drivers", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("watch_conditions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("invalidation_conditions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("open_questions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("regime_assumption", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("time_horizon", sa.String(length=100), nullable=True),
        sa.Column("last_analysis_id", sa.Integer(), nullable=True),
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_asset_strategies_version_positive"),
        sa.CheckConstraint(
            "conviction >= 0.0 AND conviction <= 1.0",
            name="ck_asset_strategies_conviction_probability",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="asset_strategies_user_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_analysis_id"],
            ["analysis_results.id"],
            name="asset_strategies_last_analysis_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_strategies_user_id", "asset_strategies", ["user_id"], unique=False)
    op.create_index("ix_asset_strategies_ticker", "asset_strategies", ["ticker"], unique=False)
    op.create_index("ix_asset_strategies_status", "asset_strategies", ["status"], unique=False)
    op.create_index("ix_asset_strategies_last_analysis_id", "asset_strategies", ["last_analysis_id"], unique=False)
    op.create_index(
        "ix_asset_strategies_owner_ticker_asset_type",
        "asset_strategies",
        ["user_id", "ticker", "asset_type"],
        unique=False,
    )
    op.create_index(
        "ix_asset_strategies_effective_recorded",
        "asset_strategies",
        ["effective_at", "recorded_at"],
        unique=False,
    )
    # This expression-based partial index is intentionally raw SQL: Alembic's
    # generic create_index cannot express a COALESCE expression consistently.
    # The statement is valid on both production PostgreSQL and SQLite's local
    # development/test dialect, which avoids NULL allowing duplicate global
    # active strategies.
    op.execute(
        "CREATE UNIQUE INDEX uq_asset_strategies_active_owner_ticker_asset_type "
        "ON asset_strategies (COALESCE(user_id, -1), ticker, asset_type) "
        "WHERE status = 'ACTIVE'"
    )

    op.create_table(
        "asset_strategy_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=True),
        sa.Column("revision_action", sa.String(length=30), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("triggered_invalidations", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("regime_before", sa.JSON(), nullable=True),
        sa.Column("regime_after", sa.JSON(), nullable=True),
        sa.Column("pm_proposed_rating", sa.String(length=30), nullable=True),
        sa.Column("accepted_rating", sa.String(length=30), nullable=True),
        sa.Column("change_strength", sa.Float(), nullable=True),
        sa.Column(
            "effective_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("version > 0", name="ck_asset_strategy_versions_version_positive"),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["asset_strategies.id"],
            name="asset_strategy_versions_strategy_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analysis_results.id"],
            name="asset_strategy_versions_analysis_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "version", name="uq_asset_strategy_versions_strategy_version"),
    )
    op.create_index("ix_asset_strategy_versions_strategy_id", "asset_strategy_versions", ["strategy_id"], unique=False)
    op.create_index("ix_asset_strategy_versions_analysis_id", "asset_strategy_versions", ["analysis_id"], unique=False)
    op.create_index(
        "ix_asset_strategy_versions_effective_at",
        "asset_strategy_versions",
        ["effective_at"],
        unique=False,
    )
    op.create_index(
        "ix_asset_strategy_versions_recorded_at",
        "asset_strategy_versions",
        ["recorded_at"],
        unique=False,
    )
    op.create_index(
        "ix_asset_strategy_versions_strategy_effective_recorded",
        "asset_strategy_versions",
        ["strategy_id", "effective_at", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_asset_strategy_versions_strategy_effective_recorded", table_name="asset_strategy_versions")
    op.drop_index("ix_asset_strategy_versions_recorded_at", table_name="asset_strategy_versions")
    op.drop_index("ix_asset_strategy_versions_effective_at", table_name="asset_strategy_versions")
    op.drop_index("ix_asset_strategy_versions_analysis_id", table_name="asset_strategy_versions")
    op.drop_index("ix_asset_strategy_versions_strategy_id", table_name="asset_strategy_versions")
    op.drop_table("asset_strategy_versions")

    op.execute("DROP INDEX IF EXISTS uq_asset_strategies_active_owner_ticker_asset_type")
    op.drop_index("ix_asset_strategies_effective_recorded", table_name="asset_strategies")
    op.drop_index("ix_asset_strategies_owner_ticker_asset_type", table_name="asset_strategies")
    op.drop_index("ix_asset_strategies_last_analysis_id", table_name="asset_strategies")
    op.drop_index("ix_asset_strategies_status", table_name="asset_strategies")
    op.drop_index("ix_asset_strategies_ticker", table_name="asset_strategies")
    op.drop_index("ix_asset_strategies_user_id", table_name="asset_strategies")
    op.drop_table("asset_strategies")
