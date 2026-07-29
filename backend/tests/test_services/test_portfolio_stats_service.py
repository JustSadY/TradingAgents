from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.portfolio_stats_service import _closing_cost_basis, _closing_orders, _equity_max_drawdown_pct


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


def test_closing_cost_basis_and_returns_include_the_opening_fee():
    # A $1,000 long with $1 opening and $1.20 exit commission closes at
    # $1,200.  All-in P&L is $197.80 and the capital committed was $1,001.
    order = _order(action="SELL", side="long", status="FILLED", total_value="1200", commission="1.2")
    order.entry_commission = Decimal("1.0")

    assert _closing_cost_basis(order, Decimal("197.8")) == Decimal("1001.0")


def test_max_drawdown_uses_portfolio_equity_not_cumulative_pnl_zero_baseline():
    # A $1,000 profit followed by a $1,000 loss returns a $100,000 account to
    # its starting equity.  It is a ~0.99% drawdown from the $101,000 peak,
    # not a nonsensical -100% drawdown from a $1,000 P&L peak.
    orders = [
        SimpleNamespace(realized_pnl=Decimal("1000")),
        SimpleNamespace(realized_pnl=Decimal("-1000")),
    ]

    assert _equity_max_drawdown_pct(Decimal("100000"), orders) == pytest.approx(-(1000 / 101000 * 100))
