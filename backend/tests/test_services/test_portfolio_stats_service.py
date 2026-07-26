from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from backend.services.portfolio_stats_service import _closing_cost_basis, _closing_orders


def _order(*, action: str, side: str, status: str, total_value: str = "1000", commission: str = "1"):
    return SimpleNamespace(
        action=action,
        side=side,
        status=status,
        total_value=Decimal(total_value),
        commission=Decimal(commission),
    )


def test_closing_orders_include_automatic_exits_and_short_covers_only():
    long_entry = _order(action="BUY", side="long", status="FILLED")
    long_stop = _order(action="SELL", side="long", status="STOP_LOSS")
    short_entry = _order(action="SELL", side="short", status="FILLED")
    short_take_profit = _order(action="BUY", side="short", status="TAKE_PROFIT")
    short_liquidation = _order(action="BUY", side="short", status="LIQUIDATED")

    closed = _closing_orders([long_entry, long_stop, short_entry, short_take_profit, short_liquidation])

    assert closed == [long_stop, short_take_profit, short_liquidation]


def test_closing_cost_basis_is_directionally_correct_for_long_and_short():
    # Long: exit 900, P&L -100.9, exit commission .9 => entry notional 1,000.
    long_order = _order(action="SELL", side="long", status="STOP_LOSS", total_value="900", commission="0.9")
    assert _closing_cost_basis(long_order, Decimal("-100.9")) == Decimal("1000.0")

    # Short: cover 900, P&L 99.1, exit commission .9 => entry notional 1,000.
    short_order = _order(action="BUY", side="short", status="TAKE_PROFIT", total_value="900", commission="0.9")
    assert _closing_cost_basis(short_order, Decimal("99.1")) == Decimal("1000.0")
