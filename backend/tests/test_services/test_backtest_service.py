from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from backend.services.backtest_service import (
    _apply_slippage,
    _close_position,
    _generate_signal,
    _normalise_exit_levels,
    _trade_pnl,
)


class TestApplySlippage:
    def test_buy_worsens_price_upward(self):
        # 5 bps = 0.05% higher
        assert _apply_slippage(100.0, "BUY", 5.0) == 100.05

    def test_sell_worsens_price_downward(self):
        assert _apply_slippage(100.0, "SELL", 5.0) == 99.95

    def test_zero_slippage_is_a_no_op(self):
        assert _apply_slippage(123.45, "BUY", 0.0) == 123.45
        assert _apply_slippage(123.45, "SELL", 0.0) == 123.45

    def test_returns_plain_float(self):
        result = _apply_slippage(50.0, "BUY", 10.0)
        assert isinstance(result, float)


class TestTradePnl:
    def test_long_profit(self):
        # Bought at 100, sold at 110, 10 shares, no commission
        pnl = _trade_pnl("long", entry_price=100.0, exit_price=110.0, size=10.0, rate=0.0)
        assert pnl == 100.0

    def test_long_loss(self):
        pnl = _trade_pnl("long", entry_price=100.0, exit_price=90.0, size=10.0, rate=0.0)
        assert pnl == -100.0

    def test_short_profit_when_price_drops(self):
        pnl = _trade_pnl("short", entry_price=100.0, exit_price=90.0, size=10.0, rate=0.0)
        assert pnl == 100.0

    def test_commission_charged_on_both_legs(self):
        # 1000 notional in, 1100 notional out, 0.1% commission each leg
        pnl = _trade_pnl("long", entry_price=100.0, exit_price=110.0, size=10.0, rate=0.001)
        expected_gross = 100.0
        expected_commission = 1000.0 * 0.001 + 1100.0 * 0.001
        assert round(pnl, 6) == round(expected_gross - expected_commission, 6)

    def test_returns_plain_float(self):
        assert isinstance(_trade_pnl("long", 100.0, 110.0, 10.0, 0.001), float)


class TestClosePosition:
    def test_long_cash_delta_returns_sale_proceeds_without_double_counting_pnl(self):
        cash_delta, trade = _close_position(
            "long",
            entry_price=100.0,
            exit_price=110.0,
            size=10.0,
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=0.0,
        )
        # Entry notional was already removed from cash. Closing returns only
        # the sale proceeds (110*10), not sale proceeds plus the same $100 P&L.
        assert cash_delta == 1100.0
        assert trade["pnl"] == 100.0
        assert trade["return_pct"] == 10.0
        assert trade["side"] == "long"
        assert trade["reason"] == "SIGNAL"

    def test_short_cash_delta_is_pnl_only(self):
        cash_delta, trade = _close_position(
            "short",
            entry_price=100.0,
            exit_price=90.0,
            size=10.0,
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="TAKE_PROFIT",
            rate=0.0,
        )
        assert cash_delta == 100.0
        assert trade["pnl"] == 100.0

    def test_exit_cash_flows_charge_each_commission_leg_once(self):
        # $1,000 initial cash: buy 1 @100, sell @110, 0.1% commission each
        # leg.  Cash after open is 899.90 and close returns 109.89 = 1,009.79.
        cash_delta, trade = _close_position(
            "long",
            entry_price=100.0,
            exit_price=110.0,
            size=1.0,
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=0.001,
        )
        assert cash_delta == 109.89
        assert round(1000.0 - 100.0 - 0.1 + cash_delta, 2) == 1009.79
        assert trade["pnl"] == 9.79

    def test_short_exit_does_not_charge_entry_commission_twice(self):
        # The short entry commission is deducted when opening.  Closing only
        # deducts the buy-to-cover commission from gross P&L.
        cash_delta, trade = _close_position(
            "short",
            entry_price=100.0,
            exit_price=90.0,
            size=1.0,
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=0.001,
        )
        assert cash_delta == 9.91
        assert round(1000.0 - 0.1 + cash_delta, 2) == 1009.81
        assert trade["pnl"] == 9.81

    def test_return_pct_matches_pnl_over_cost_basis(self):
        _, trade = _close_position(
            "long",
            entry_price=50.0,
            exit_price=55.0,
            size=4.0,
            entry_date="2024-01-01",
            exit_date="2024-01-02",
            reason="SIGNAL",
            rate=0.0,
        )
        # pnl = (55-50)*4 = 20; cost basis = 50*4 = 200; return = 10%
        assert trade["pnl"] == 20.0
        assert trade["return_pct"] == 10.0

    def test_prices_rounded_to_cents_in_trade_record(self):
        _, trade = _close_position(
            "long",
            entry_price=100.123456,
            exit_price=110.987654,
            size=1.0,
            entry_date="2024-01-01",
            exit_date="2024-01-02",
            reason="SIGNAL",
            rate=0.0,
        )
        assert trade["entry_price"] == 100.12
        assert trade["exit_price"] == 110.99


class TestNormaliseExitLevels:
    def test_short_discards_long_oriented_annotation_levels(self):
        stop, target = _normalise_exit_levels("short", 100.0, 95.0, 110.0)
        assert stop == 105.0
        assert target == 90.0

    def test_long_keeps_valid_levels(self):
        stop, target = _normalise_exit_levels("long", 100.0, 95.0, 110.0)
        assert stop == 95.0
        assert target == 110.0


class TestConsensusTiming:
    def test_consensus_requires_a_prior_trading_date_signal(self):
        row = pd.Series({"Date": pd.Timestamp("2024-01-03")})
        data = pd.DataFrame([row])
        analysis = SimpleNamespace(signal="Buy", chart_annotations={})
        analyses = {"2024-01-03": analysis}

        signal, _, _ = _generate_signal(data, row, "consensus", analyses)
        assert signal is None

        signal, _, _ = _generate_signal(
            data,
            row,
            "consensus",
            analyses,
            consensus_signal_date="2024-01-03",
        )
        assert signal == "BUY"
