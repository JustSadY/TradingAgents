"""Rule-based backtest strategies accept tunable parameters.

MACD periods and the RSI thresholds used to be hardcoded, which left nothing
for an optimizer to search over. The simulation owns the parameter space so a
caller cannot hand an indicator a value it would raise on.
"""

from __future__ import annotations

import pytest

from backend.services.backtest_service import (
    STRATEGY_PARAM_SPACE,
    normalise_strategy_params,
    strategy_defaults,
)


class TestDefaults:
    def test_defaults_reproduce_the_previous_hardcoded_behaviour(self):
        assert strategy_defaults("macd_crossover") == {
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
        }
        assert strategy_defaults("rsi_oversold") == {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        }

    def test_a_strategy_without_tunables_has_no_parameters(self):
        assert strategy_defaults("consensus") == {}
        assert normalise_strategy_params("consensus", {"macd_fast": 5}) == {}

    def test_every_declared_default_sits_inside_its_own_bounds(self):
        for strategy, space in STRATEGY_PARAM_SPACE.items():
            for key, spec in space.items():
                assert spec["min"] <= spec["default"] <= spec["max"], f"{strategy}.{key}"


class TestNormalisation:
    def test_none_yields_the_defaults(self):
        assert normalise_strategy_params("rsi_oversold", None) == strategy_defaults("rsi_oversold")

    def test_supplied_values_are_applied(self):
        resolved = normalise_strategy_params("rsi_oversold", {"rsi_period": 21})
        assert resolved["rsi_period"] == 21

    def test_out_of_range_values_are_clamped_rather_than_rejected(self):
        """A sampler proposes freely; the simulation decides what is runnable."""
        resolved = normalise_strategy_params("rsi_oversold", {"rsi_period": 9999})
        assert resolved["rsi_period"] == STRATEGY_PARAM_SPACE["rsi_oversold"]["rsi_period"]["max"]

        resolved = normalise_strategy_params("macd_crossover", {"macd_fast": -50})
        assert resolved["macd_fast"] == STRATEGY_PARAM_SPACE["macd_crossover"]["macd_fast"]["min"]

    def test_unknown_keys_are_dropped(self):
        resolved = normalise_strategy_params("rsi_oversold", {"nonsense": 1, "rsi_period": 20})
        assert "nonsense" not in resolved
        assert resolved["rsi_period"] == 20

    @pytest.mark.parametrize("value", ["abc", None, [], {}])
    def test_non_numeric_values_fall_back_to_the_default(self, value):
        resolved = normalise_strategy_params("rsi_oversold", {"rsi_period": value})
        assert resolved["rsi_period"] == 14

    def test_a_fast_macd_period_is_kept_below_the_slow_one(self):
        """Otherwise the crossover's meaning inverts and the run is nonsense."""
        resolved = normalise_strategy_params("macd_crossover", {"macd_fast": 30, "macd_slow": 10})
        assert resolved["macd_fast"] < resolved["macd_slow"]

    def test_rsi_bands_are_kept_ordered(self):
        resolved = normalise_strategy_params("rsi_oversold", {"rsi_oversold": 45, "rsi_overbought": 55})
        assert resolved["rsi_oversold"] < resolved["rsi_overbought"]

        resolved = normalise_strategy_params("rsi_oversold", {"rsi_oversold": 40, "rsi_overbought": 40})
        assert resolved["rsi_oversold"] < resolved["rsi_overbought"]

    def test_normalisation_is_idempotent(self):
        once = normalise_strategy_params("macd_crossover", {"macd_fast": 30, "macd_slow": 10})
        assert normalise_strategy_params("macd_crossover", once) == once
