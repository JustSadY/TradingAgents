from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services.backtest_service import (
    _apply_slippage_decimal,
    _close_position_decimal,
    _compute_metrics,
    _exit_reason_and_price,
    _generate_signal,
    _normalise_exit_levels,
    _trade_pnl_decimal,
)


class TestApplySlippage:
    """Exercises the Decimal implementation the simulator actually uses."""

    def test_buy_worsens_price_upward(self):
        assert _apply_slippage_decimal(Decimal("100"), "BUY", Decimal("5")) == Decimal("100.05")

    def test_sell_worsens_price_downward(self):
        assert _apply_slippage_decimal(Decimal("100"), "SELL", Decimal("5")) == Decimal("99.95")

    def test_zero_slippage_is_a_no_op(self):
        assert _apply_slippage_decimal(Decimal("123.45"), "BUY", Decimal("0")) == Decimal("123.45")
        assert _apply_slippage_decimal(Decimal("123.45"), "SELL", Decimal("0")) == Decimal("123.45")

    def test_stays_in_decimal(self):
        """Money never round-trips through float in the simulation path."""
        assert isinstance(_apply_slippage_decimal(Decimal("50"), "BUY", Decimal("10")), Decimal)

class TestTradePnl:
    @staticmethod
    def _pnl(side, entry, exit_, size, rate):
        return _trade_pnl_decimal(side, Decimal(entry), Decimal(exit_), Decimal(size), Decimal(rate))

    def test_long_profit(self):
        assert self._pnl("long", "100", "110", "10", "0") == Decimal("100")

    def test_long_loss(self):
        assert self._pnl("long", "100", "90", "10", "0") == Decimal("-100")

    def test_short_profit_when_price_drops(self):
        assert self._pnl("short", "100", "90", "10", "0") == Decimal("100")

    def test_commission_charged_on_both_legs(self):
        pnl = self._pnl("long", "100", "110", "10", "0.001")
        expected_commission = Decimal("1000") * Decimal("0.001") + Decimal("1100") * Decimal("0.001")
        assert pnl == Decimal("100") - expected_commission

    def test_stays_in_decimal(self):
        assert isinstance(self._pnl("long", "100", "110", "10", "0.001"), Decimal)

class TestClosePosition:
    def test_long_cash_delta_returns_sale_proceeds_without_double_counting_pnl(self):
        cash_delta, trade = _close_position_decimal(
            "long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("110.0"),
            size=Decimal("10.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=Decimal("0.0"),
        )
        assert cash_delta == Decimal("1100")
        assert trade["pnl"] == Decimal("100.0")
        assert trade["return_pct"] == Decimal("10.0")
        assert trade["side"] == "long"
        assert trade["reason"] == "SIGNAL"

    def test_short_cash_delta_is_pnl_only(self):
        cash_delta, trade = _close_position_decimal(
            "short",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("90.0"),
            size=Decimal("10.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="TAKE_PROFIT",
            rate=Decimal("0.0"),
        )
        assert cash_delta == Decimal("100.0")
        assert trade["pnl"] == Decimal("100.0")

    def test_exit_cash_flows_charge_each_commission_leg_once(self):
        cash_delta, trade = _close_position_decimal(
            "long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("110.0"),
            size=Decimal("1.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=Decimal("0.001"),
        )
        assert cash_delta == Decimal("109.89")
        assert round(Decimal("1000") - Decimal("100") - Decimal("0.1") + cash_delta, 2) == Decimal("1009.79")
        assert trade["pnl"] == 9.79

    def test_short_exit_does_not_charge_entry_commission_twice(self):
        cash_delta, trade = _close_position_decimal(
            "short",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("90.0"),
            size=Decimal("1.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-05",
            reason="SIGNAL",
            rate=Decimal("0.001"),
        )
        assert cash_delta == Decimal("9.91")
        assert round(Decimal("1000") - Decimal("0.1") + cash_delta, 2) == Decimal("1009.81")
        assert trade["pnl"] == 9.81

    def test_return_pct_matches_pnl_over_cost_basis(self):
        _, trade = _close_position_decimal(
            "long",
            entry_price=Decimal("50.0"),
            exit_price=Decimal("55.0"),
            size=Decimal("4.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-02",
            reason="SIGNAL",
            rate=Decimal("0.0"),
        )
        assert trade["pnl"] == 20.0
        assert trade["return_pct"] == Decimal("10.0")

    def test_prices_rounded_to_cents_in_trade_record(self):
        _, trade = _close_position_decimal(
            "long",
            entry_price=Decimal("100.123456"),
            exit_price=Decimal("110.987654"),
            size=Decimal("1.0"),
            entry_date="2024-01-01",
            exit_date="2024-01-02",
            reason="SIGNAL",
            rate=Decimal("0.0"),
        )
        assert trade["entry_price"] == 100.12
        assert trade["exit_price"] == 110.99

    def test_decimal_close_keeps_cash_and_fee_math_exact_until_serialization(self):
        cash_delta, trade = _close_position_decimal(
            "long",
            Decimal("100"),
            Decimal("110"),
            Decimal("1"),
            "2024-01-01",
            "2024-01-05",
            "SIGNAL",
            Decimal("0.001"),
        )

        assert isinstance(cash_delta, Decimal)
        assert cash_delta == Decimal("109.8900")
        assert trade["pnl"] == 9.79

    def test_short_financing_is_reported_without_double_debiting_close_cash(self):
        cash_delta, trade = _close_position_decimal(
            "short",
            Decimal("100"),
            Decimal("90"),
            Decimal("10"),
            "2024-01-01",
            "2024-01-05",
            "SIGNAL",
            Decimal("0"),
            Decimal("2"),
        )

        assert cash_delta == Decimal("100")
        assert trade["pnl"] == 98.0
        assert trade["financing_cost"] == 2.0


def test_intrabar_stop_is_conservatively_prioritized_over_target():
    reason, price = _exit_reason_and_price(
        "long",
        Decimal("100"),
        Decimal("112"),
        Decimal("94"),
        Decimal("105"),
        Decimal("95"),
        Decimal("110"),
        1,
    )

    assert reason == "STOP_LOSS"
    assert price == Decimal("95")

def test_backtest_metrics_take_decimal_equity_curve_without_float_money_rounding():
    metrics = _compute_metrics(
        [Decimal("100000.0001"), Decimal("101000.0001"), Decimal("100000.0001")],
        [{"pnl": 1000.0}, {"pnl": -1000.0}],
        Decimal("100000.0001"),
    )

    assert metrics["final_value"] == 100000.0
    assert metrics["max_drawdown"] == pytest.approx(-(1000 / 101000.0001 * 100), abs=0.01)

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
