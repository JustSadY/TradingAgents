from __future__ import annotations

from backend.services.trading_orchestrator import _classify_order_intent, _directional_exit_levels, _position_quantity


class TestPositionQuantity:
    def test_basic_risk_based_sizing_no_stop_loss(self):
        qty = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0)
        assert qty == 40.0

    def test_sizing_with_stop_loss_uses_risk_per_share(self):
        qty = _position_quantity(
            risk_per_trade_pct=2.0,
            capital=100_000.0,
            price=50.0,
            stop_loss=45.0,
            max_position_size_pct=100.0,
        )
        assert qty == 400.0

    def test_max_allocation_cap_applies(self):
        qty = _position_quantity(
            risk_per_trade_pct=50.0,
            capital=100_000.0,
            price=10.0,
            max_position_size_pct=5.0,
        )
        assert qty == 500.0

    def test_kelly_multiplier_scales_down_risk(self):
        full_qty = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0)
        half_qty = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0, kelly_multiplier=0.5)
        assert half_qty == full_qty / 2

    def test_kelly_multiplier_clamped_to_0_1_range(self):
        capped = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0, kelly_multiplier=5.0)
        base = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0, kelly_multiplier=1.0)
        assert capped == base

        negative = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0, kelly_multiplier=-1.0)
        assert negative == 0.0

    def test_stop_loss_equal_to_price_is_ignored(self):
        qty = _position_quantity(risk_per_trade_pct=2.0, capital=100_000.0, price=50.0, stop_loss=50.0)
        assert qty == 40.0

    def test_returns_plain_float(self):
        assert isinstance(_position_quantity(2.0, 100_000.0, 50.0), float)

    def test_minimum_risk_per_share_floor_prevents_oversizing(self):
        qty = _position_quantity(
            risk_per_trade_pct=0.1,
            capital=100_000.0,
            price=100.0,
            stop_loss=99.999,
            max_position_size_pct=100.0,
        )
        floor_risk_per_share = 0.005 * 100.0
        expected = (0.1 / 100.0 * 100_000.0) / floor_risk_per_share
        assert round(qty, 6) == round(expected, 6)
        assert qty == 200.0

class TestOrderIntent:
    def test_exit_intents_close_existing_positions_even_when_shorting_is_disabled(self):
        assert _classify_order_intent("SELL", "long", allow_short=False) == "close_long"
        assert _classify_order_intent("BUY", "short", allow_short=False) == "close_short"

    def test_sell_without_a_long_does_not_open_short_when_disabled(self):
        assert _classify_order_intent("SELL", None, allow_short=False) is None

    def test_sell_without_a_long_opens_short_only_when_enabled(self):
        assert _classify_order_intent("SELL", None, allow_short=True) == "open_short"

class TestDirectionalExitLevels:
    def test_short_rejects_long_oriented_stop_and_target(self):
        stop, target = _directional_exit_levels("short", 100.0, 95.0, 110.0)
        assert stop is None
        assert target is None

    def test_short_keeps_directionally_valid_levels(self):
        stop, target = _directional_exit_levels("short", 100.0, 105.0, 90.0)
        assert stop == 105.0
        assert target == 90.0


class TestTargetAllocationRecovery:
    """A Buy whose model omitted ``position_size_pct``.

    The field is the sole sizing input, so an omission used to skip the order
    with a message about the allocation being "missing or invalid" — which
    reads as a portfolio problem rather than as the model having left out one
    number it was asked for. ``suggested_capital`` states the same intent in a
    different unit, and for an opening position the two are the same quantity.
    """

    @staticmethod
    def _row(**decision):
        from types import SimpleNamespace

        return SimpleNamespace(portfolio_decision_json=dict(decision))

    def test_an_opening_position_is_sized_from_suggested_capital(self):
        from backend.services.trading_orchestrator import _target_notional_from_suggested_capital

        row = self._row(rating="Buy", position_size_pct=None, suggested_capital=70_000.0)

        assert _target_notional_from_suggested_capital(row, ticker="NVDA", existing_notional=0.0) == 70_000.0

    def test_an_existing_position_is_never_resized_from_suggested_capital(self):
        """It is this order's notional, not the total to hold afterwards."""
        from backend.services.trading_orchestrator import _target_notional_from_suggested_capital

        row = self._row(rating="Buy", position_size_pct=None, suggested_capital=70_000.0)

        assert _target_notional_from_suggested_capital(row, ticker="NVDA", existing_notional=1_000.0) is None

    def test_no_recovery_without_a_usable_capital_figure(self):
        from backend.services.trading_orchestrator import _target_notional_from_suggested_capital

        for value in (None, 0.0, "n/a"):
            row = self._row(rating="Buy", position_size_pct=None, suggested_capital=value)
            assert _target_notional_from_suggested_capital(row, ticker="NVDA", existing_notional=0.0) is None

    def test_a_present_percentage_still_wins(self):
        from backend.services.trading_orchestrator import _pm_target_notional

        row = self._row(rating="Buy", position_size_pct=12.5, suggested_capital=70_000.0)

        assert _pm_target_notional(row, portfolio_equity=200_000.0) == 25_000.0
