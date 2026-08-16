"""Backfill canonical portfolio decisions from historical chart annotations.

Revision ID: ef56a7b8c9d0
Revises: de45f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ef56a7b8c9d0"
down_revision: str | None = "de45f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE analysis_results "
            "SET portfolio_decision_json = CASE "
            "WHEN json_typeof(chart_annotations -> 'portfolio_decision') = 'object' "
            "THEN chart_annotations -> 'portfolio_decision' "
            "WHEN json_typeof(chart_annotations -> 'portfolio_decision_json') = 'object' "
            "THEN chart_annotations -> 'portfolio_decision_json' "
            "ELSE portfolio_decision_json END "
            "WHERE portfolio_decision_json IS NULL AND chart_annotations IS NOT NULL "
            "AND (json_typeof(chart_annotations -> 'portfolio_decision') = 'object' "
            "OR json_typeof(chart_annotations -> 'portfolio_decision_json') = 'object')"
        )
    )


def downgrade() -> None:
    pass
