"""canonicalize analysis signal values

Revision ID: d7e8f9a0b1c2
Revises: b129d730127d
Create Date: 2026-07-29 00:03:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "b129d730127d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Recognised historical spellings have exactly the same meaning as the
    # current enum. Leave unknown text intact: data migrations must not erase
    # information merely because it cannot be represented by the API today.
    op.execute(
        """
        UPDATE analysis_results
        SET signal = CASE lower(trim(signal))
            WHEN 'buy' THEN 'Buy'
            WHEN 'overweight' THEN 'Overweight'
            WHEN 'hold' THEN 'Hold'
            WHEN 'underweight' THEN 'Underweight'
            WHEN 'sell' THEN 'Sell'
        END
        WHERE lower(trim(signal)) IN ('buy', 'overweight', 'hold', 'underweight', 'sell')
        """
    )


def downgrade() -> None:
    # Case normalization is intentionally one-way. Restoring arbitrary
    # original casing is impossible and would not restore any business data.
    pass
