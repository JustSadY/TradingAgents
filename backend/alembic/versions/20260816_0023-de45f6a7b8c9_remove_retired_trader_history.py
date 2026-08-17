"""remove retired Trader history columns

Revision ID: de45f6a7b8c9
Revises: cd34e5f6a7b8
Create Date: 2026-08-16 14:45:00.000000+00:00

Trader was an intermediate execution-planner agent in an older graph. Current
runs no longer write its text/JSON columns and the canonical persisted outcome
is ``final_decision``. Preserve the only authoritative gap by copying the old
Trader text into ``final_decision`` when that field is empty, then remove the
retired intermediate artifacts.

``trader_proposal_json`` is deliberately not copied into
``portfolio_decision_json``: the old payload described a Trader proposal
(``action``, Kelly sizing, etc.), not a Portfolio Manager/controller accepted
decision. Treating it as canonical would rewrite historical semantics.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "de45f6a7b8c9"
down_revision: str | None = "cd34e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE analysis_results
               SET final_decision = trader_plan
             WHERE (final_decision IS NULL OR btrim(final_decision) = '')
               AND trader_plan IS NOT NULL
               AND btrim(trader_plan) <> ''
            """
        )
    )
    op.drop_column("analysis_results", "trader_proposal_json")
    op.drop_column("analysis_results", "trader_plan")


def downgrade() -> None:
    # Schema downgrade only. The retired intermediate proposal is intentionally
    # not reconstructed from the canonical final decision because that would
    # invent historical Trader output that may never have existed.
    op.add_column(
        "analysis_results",
        sa.Column("trader_plan", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.add_column(
        "analysis_results",
        sa.Column("trader_proposal_json", sa.Text(), server_default=sa.text("'{}'"), nullable=False),
    )
