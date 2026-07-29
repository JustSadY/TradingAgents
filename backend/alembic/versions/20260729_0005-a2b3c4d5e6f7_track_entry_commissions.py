"""track opening commissions through simulated position closes

Revision ID: a2b3c4d5e6f7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-29 10:00:00.000000+00:00

The simulation previously charged an opening commission to cash but discarded
it from the holding.  Closing P&L therefore omitted that cost, and historical
performance/debriefs overstated results.  Carry the exact fee on holdings and
persist its pro-rata portion on closing orders.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    return column in {item["name"] for item in inspector.get_columns(table)}


def _add_money_column(table: str, column: str) -> bool:
    if _has_column(table, column):
        return False
    op.add_column(
        table,
        sa.Column(column, sa.Numeric(precision=20, scale=8), nullable=False, server_default=sa.text("0")),
    )
    op.alter_column(table, column, server_default=None)
    return True


def _backfill_simulated_orders() -> None:
    # Only simulation portfolios use the local fixed commission model.  Live
    # broker fills may have provider-specific fees, so do not infer them.
    op.execute(
        """
        UPDATE orders AS o
        SET entry_commission = COALESCE(o.commission, 0)
        FROM portfolios AS p
        WHERE p.id = o.portfolio_id
          AND p.mode = 'simulation'
          AND (
              (lower(COALESCE(o.side, 'long')) = 'long' AND upper(o.action) = 'BUY')
              OR (lower(COALESCE(o.side, 'long')) = 'short' AND upper(o.action) = 'SELL')
          )
        """
    )
    # Old closing realized_pnl includes the exit fee but not the opening fee.
    # Reconstruct the entry notional from the recorded closing fill, then
    # charge the fixed 10 bps entry fee exactly once.
    op.execute(
        """
        WITH closing_orders AS (
            SELECT
                o.id,
                round(
                    greatest(
                        CASE
                            WHEN lower(COALESCE(o.side, 'long')) = 'short' THEN
                                COALESCE(o.total_value, 0) + COALESCE(o.realized_pnl, 0) + COALESCE(o.commission, 0)
                            ELSE
                                COALESCE(o.total_value, 0) - COALESCE(o.realized_pnl, 0) - COALESCE(o.commission, 0)
                        END,
                        0
                    ) * 0.001,
                    4
                ) AS opening_fee
            FROM orders AS o
            JOIN portfolios AS p ON p.id = o.portfolio_id
            WHERE p.mode = 'simulation'
              AND upper(COALESCE(o.status, '')) IN ('FILLED', 'STOP_LOSS', 'TAKE_PROFIT', 'LIQUIDATED')
              AND (
                  (lower(COALESCE(o.side, 'long')) = 'long' AND upper(o.action) = 'SELL')
                  OR (lower(COALESCE(o.side, 'long')) = 'short' AND upper(o.action) = 'BUY')
              )
        )
        UPDATE orders AS o
        SET entry_commission = c.opening_fee,
            realized_pnl = COALESCE(o.realized_pnl, 0) - c.opening_fee
        FROM closing_orders AS c
        WHERE o.id = c.id
        """
    )


def upgrade() -> None:
    added_holding_fee = _add_money_column("holdings", "entry_commission")
    added_order_fee = _add_money_column("orders", "entry_commission")

    if added_holding_fee:
        # Existing open positions have no exact fee ledger.  The simulator has
        # always charged a fixed 10 bps opening fee, so this is the closest
        # recoverable value; new positions preserve their exact per-fill sum.
        op.execute(
            """
            UPDATE holdings AS h
            SET entry_commission = round(greatest(h.avg_buy_price * h.quantity, 0) * 0.001, 4)
            FROM portfolios AS p
            WHERE p.id = h.portfolio_id
              AND p.mode = 'simulation'
            """
        )
    if added_order_fee:
        _backfill_simulated_orders()


def downgrade() -> None:
    if _has_column("orders", "entry_commission"):
        # Restore historical simulation closing P&L semantics before removing
        # the supporting field.  Live orders were deliberately untouched.
        op.execute(
            """
            UPDATE orders AS o
            SET realized_pnl = COALESCE(o.realized_pnl, 0) + COALESCE(o.entry_commission, 0)
            FROM portfolios AS p
            WHERE p.id = o.portfolio_id
              AND p.mode = 'simulation'
              AND upper(COALESCE(o.status, '')) IN ('FILLED', 'STOP_LOSS', 'TAKE_PROFIT', 'LIQUIDATED')
              AND (
                  (lower(COALESCE(o.side, 'long')) = 'long' AND upper(o.action) = 'SELL')
                  OR (lower(COALESCE(o.side, 'long')) = 'short' AND upper(o.action) = 'BUY')
              )
            """
        )
        op.drop_column("orders", "entry_commission")
    if _has_column("holdings", "entry_commission"):
        op.drop_column("holdings", "entry_commission")
