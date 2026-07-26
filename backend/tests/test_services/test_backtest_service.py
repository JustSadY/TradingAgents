from __future__ import annotations

from backend.services.backtest_service import _apply_slippage, _close_position, _trade_pnl


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
    def test_long_cash_delta_is_notional_plus_pnl(self):
        cash_delta, trade = _close_position(
            "long", entry_price=100.0, exit_price=110.0, size=10.0,
            entry_date="2024-01-01", exit_date="2024-01-05", reason="SIGNAL", rate=0.0,
        )
        # Notional returned (110*10=1100) plus the 100 pnl
        assert cash_delta == 1200.0
        assert trade["pnl"] == 100.0
        assert trade["return_pct"] == 10.0
        assert trade["side"] == "long"
        assert trade["reason"] == "SIGNAL"

    def test_short_cash_delta_is_pnl_only(self):
        cash_delta, trade = _close_position(
            "short", entry_price=100.0, exit_price=90.0, size=10.0,
            entry_date="2024-01-01", exit_date="2024-01-05", reason="TAKE_PROFIT", rate=0.0,
        )
        assert cash_delta == 100.0
        assert trade["pnl"] == 100.0

    def test_return_pct_matches_pnl_over_cost_basis(self):
        _, trade = _close_position(
            "long", entry_price=50.0, exit_price=55.0, size=4.0,
            entry_date="2024-01-01", exit_date="2024-01-02", reason="SIGNAL", rate=0.0,
        )
        # pnl = (55-50)*4 = 20; cost basis = 50*4 = 200; return = 10%
        assert trade["pnl"] == 20.0
        assert trade["return_pct"] == 10.0

    def test_prices_rounded_to_cents_in_trade_record(self):
        _, trade = _close_position(
            "long", entry_price=100.123456, exit_price=110.987654, size=1.0,
            entry_date="2024-01-01", exit_date="2024-01-02", reason="SIGNAL", rate=0.0,
        )
        assert trade["entry_price"] == 100.12
        assert trade["exit_price"] == 110.99
