"""persist strategy-aware analysis and decision-stability contracts

Revision ID: 6e7f8091a2b3
Revises: 5d6e7f8091a2
Create Date: 2026-08-08 00:30:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6e7f8091a2b3"
down_revision: str | None = "5d6e7f8091a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Human-facing research text remains in its existing columns. These JSON
    # fields are deliberately independent machine contracts; no later node has
    # to parse Markdown to recover a strategy, regime, or accepted decision.
    for name in (
        "analysis_plan_json",
        "synthesis_json",
        "market_regime_json",
        "strategy_before_json",
        "strategy_after_json",
        "strategy_candidate_json",
        "pm_proposal_json",
        "portfolio_decision_json",
        "decision_transition_json",
    ):
        op.add_column("analysis_results", sa.Column(name, sa.JSON(), nullable=True))
    op.add_column("analysis_results", sa.Column("calibrated_confidence", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("strategy_update_status", sa.String(length=30), nullable=True))
    op.add_column("analysis_results", sa.Column("strategy_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "analysis_results_strategy_id_fkey",
        "analysis_results",
        "asset_strategies",
        ["strategy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_analysis_results_strategy_id", "analysis_results", ["strategy_id"], unique=False)
    op.add_column("analysis_results", sa.Column("strategy_before_version", sa.Integer(), nullable=True))
    op.add_column("analysis_results", sa.Column("strategy_after_version", sa.Integer(), nullable=True))
    op.add_column(
        "analysis_results",
        sa.Column("analysis_mode", sa.String(length=20), nullable=False, server_default="live"),
    )
    op.create_index("ix_analysis_results_analysis_mode", "analysis_results", ["analysis_mode"], unique=False)
    op.add_column(
        "analysis_results",
        sa.Column("learning_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_analysis_results_learning_eligible", "analysis_results", ["learning_eligible"], unique=False)
    op.alter_column("analysis_results", "analysis_mode", server_default=None)
    op.alter_column("analysis_results", "learning_eligible", server_default=None)

    # Shadow mode is deliberate. Existing deployments gain observability first
    # and cannot begin enforcing hysteresis merely by applying a migration.
    op.add_column("app_settings", sa.Column("strategy_learning_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("decision_stability_mode", sa.String(length=20), nullable=False, server_default="shadow"))
    op.add_column("app_settings", sa.Column("decision_stability_min_quality", sa.Integer(), nullable=False, server_default="70"))
    op.add_column("app_settings", sa.Column("decision_stability_min_confidence", sa.Float(), nullable=False, server_default="0.65"))
    op.add_column("app_settings", sa.Column("decision_stability_min_evidence_groups", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("app_settings", sa.Column("reversal_verifier_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("app_settings", sa.Column("confidence_calibration_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("app_settings", sa.Column("regime_aware_weighting_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name in (
        "strategy_learning_enabled",
        "decision_stability_mode",
        "decision_stability_min_quality",
        "decision_stability_min_confidence",
        "decision_stability_min_evidence_groups",
        "reversal_verifier_enabled",
        "confidence_calibration_enabled",
        "regime_aware_weighting_enabled",
    ):
        op.alter_column("app_settings", name, server_default=None)


def downgrade() -> None:
    for name in (
        "regime_aware_weighting_enabled",
        "confidence_calibration_enabled",
        "reversal_verifier_enabled",
        "decision_stability_min_evidence_groups",
        "decision_stability_min_confidence",
        "decision_stability_min_quality",
        "decision_stability_mode",
        "strategy_learning_enabled",
    ):
        op.drop_column("app_settings", name)

    op.drop_index("ix_analysis_results_learning_eligible", table_name="analysis_results")
    op.drop_column("analysis_results", "learning_eligible")
    op.drop_index("ix_analysis_results_analysis_mode", table_name="analysis_results")
    op.drop_column("analysis_results", "analysis_mode")
    op.drop_column("analysis_results", "strategy_after_version")
    op.drop_column("analysis_results", "strategy_before_version")
    op.drop_index("ix_analysis_results_strategy_id", table_name="analysis_results")
    op.drop_constraint("analysis_results_strategy_id_fkey", "analysis_results", type_="foreignkey")
    op.drop_column("analysis_results", "strategy_id")
    op.drop_column("analysis_results", "strategy_update_status")
    op.drop_column("analysis_results", "calibrated_confidence")
    for name in (
        "decision_transition_json",
        "portfolio_decision_json",
        "pm_proposal_json",
        "strategy_candidate_json",
        "strategy_after_json",
        "strategy_before_json",
        "market_regime_json",
        "synthesis_json",
        "analysis_plan_json",
    ):
        op.drop_column("analysis_results", name)
