"""Conditional volatility forecasting.

The maths is arch's; what is asserted here is the contract the risk agents and
the API depend on — units, refusal behaviour, and that the forecast is actually
conditional rather than a repackaged trailing standard deviation.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.services.volatility_service import (
    TRADING_DAYS,
    VolatilityError,
    _normal_quantile,
    describe_forecast,
    forecast_volatility,
    returns_from_prices,
)

pytest.importorskip("arch", reason="volatility forecasting requires the arch package")


def _garch_returns(rows: int = 900, seed: int = 3) -> pd.Series:
    """Simulate returns with genuine volatility clustering."""
    rng = np.random.default_rng(seed)
    omega, alpha, beta = 2e-6, 0.09, 0.89
    variance = omega / (1 - alpha - beta)
    out = np.empty(rows)
    for i in range(rows):
        shock = rng.normal(0, math.sqrt(variance))
        out[i] = shock
        variance = omega + alpha * shock**2 + beta * variance
    return pd.Series(out)


class TestNormalQuantile:
    @pytest.mark.parametrize(
        ("confidence", "expected"),
        [(0.95, 1.6448536), (0.99, 2.3263479), (0.975, 1.9599640), (0.5, 0.0)],
    )
    def test_matches_known_standard_normal_quantiles(self, confidence, expected):
        assert _normal_quantile(confidence) == pytest.approx(expected, abs=1e-6)


class TestReturnsFromPrices:
    def test_produces_log_returns_and_drops_the_first_bar(self):
        prices = pd.Series([100.0, 110.0, 121.0])
        returns = returns_from_prices(prices)

        assert len(returns) == 2
        assert returns.iloc[0] == pytest.approx(math.log(1.1))

    def test_discards_non_positive_and_non_finite_prices(self):
        prices = pd.Series([100.0, float("nan"), 0.0, -5.0, 110.0, float("inf")])
        assert returns_from_prices(prices).notna().all()


class TestForecast:
    def test_reports_annualised_fractions(self):
        forecast = forecast_volatility(_garch_returns(), horizon_days=10)

        # A simulated series around 1.5% daily sits near 20-30% annualised.
        assert 0.05 < forecast.forecast_volatility < 1.5
        assert 0.05 < forecast.realized_volatility < 1.5
        assert 0.05 < forecast.current_volatility < 1.5
        assert forecast.observations == 900
        assert forecast.converged is True

    def test_the_forecast_is_conditional_not_the_sample_deviation(self):
        """A calm sample ending in turbulence must forecast above its own mean."""
        rng = np.random.default_rng(5)
        calm = rng.normal(0, 0.004, 600)
        turbulent = rng.normal(0, 0.030, 120)
        series = pd.Series(np.concatenate([calm, turbulent]))

        forecast = forecast_volatility(series, model="garch", horizon_days=5)
        assert forecast.forecast_volatility > forecast.realized_volatility

    def test_risk_measures_scale_with_the_horizon(self):
        returns = _garch_returns()
        short = forecast_volatility(returns, horizon_days=1)
        long = forecast_volatility(returns, horizon_days=20)

        assert long.value_at_risk > short.value_at_risk
        # Expected shortfall is the average loss beyond VaR, so it is worse.
        assert long.expected_shortfall > long.value_at_risk

    def test_a_higher_confidence_demands_a_larger_loss(self):
        returns = _garch_returns()
        assert (
            forecast_volatility(returns, confidence=0.99).value_at_risk
            > forecast_volatility(returns, confidence=0.95).value_at_risk
        )

    @pytest.mark.parametrize("model", ["garch", "tarch", "egarch"])
    def test_every_declared_model_fits(self, model):
        forecast = forecast_volatility(_garch_returns(), model=model, horizon_days=5)
        assert forecast.model == model
        assert forecast.forecast_volatility > 0
        assert forecast.asymmetric is (model in {"tarch", "egarch"})

    def test_egarch_forecasts_past_one_step(self):
        """arch has no analytic multi-step EGARCH forecast; it must simulate."""
        forecast = forecast_volatility(_garch_returns(), model="egarch", horizon_days=20)
        assert forecast.forecast_volatility > 0
        assert forecast.value_at_risk > 0

    def test_a_seeded_simulation_forecast_is_reproducible(self):
        """An unseeded simulation would make the same request jitter per call."""
        returns = _garch_returns()
        first = forecast_volatility(returns, model="egarch", horizon_days=10)
        second = forecast_volatility(returns, model="egarch", horizon_days=10)
        assert first.forecast_volatility == pytest.approx(second.forecast_volatility)

    def test_annualisation_uses_the_trading_year(self):
        returns = _garch_returns()
        forecast = forecast_volatility(returns, horizon_days=1)
        daily = forecast.forecast_volatility / math.sqrt(TRADING_DAYS)
        assert 0 < daily < 0.2


class TestRefusals:
    def test_too_few_observations_is_refused(self):
        with pytest.raises(VolatilityError, match="observations are required"):
            forecast_volatility(pd.Series(np.zeros(10)))

    def test_an_unknown_model_is_refused(self):
        with pytest.raises(VolatilityError, match="Unknown volatility model"):
            forecast_volatility(_garch_returns(), model="wishful")

    @pytest.mark.parametrize("horizon", [0, -1, 500])
    def test_an_out_of_range_horizon_is_refused(self, horizon):
        with pytest.raises(VolatilityError, match="horizon_days"):
            forecast_volatility(_garch_returns(), horizon_days=horizon)

    @pytest.mark.parametrize("confidence", [0.4, 1.0, 1.5])
    def test_an_out_of_range_confidence_is_refused(self, confidence):
        with pytest.raises(VolatilityError, match="confidence"):
            forecast_volatility(_garch_returns(), confidence=confidence)

    def test_non_finite_returns_are_dropped_rather_than_poisoning_the_fit(self):
        returns = _garch_returns()
        polluted = pd.concat([returns, pd.Series([np.nan, np.inf, -np.inf])], ignore_index=True)
        assert forecast_volatility(polluted).observations == len(returns)


class TestDescription:
    def test_renders_the_numbers_an_agent_reads(self):
        forecast = forecast_volatility(_garch_returns(), model="tarch", horizon_days=10)
        text = describe_forecast("nvda", forecast)

        assert "NVDA" in text
        assert "TARCH" in text
        assert "Value at Risk" in text
        assert "Expected shortfall" in text
        assert "not a worst case" in text

    def test_warns_when_the_fitted_process_is_not_stationary(self):
        forecast = forecast_volatility(_garch_returns(), horizon_days=5)
        unstable = type(forecast)(**{**forecast.as_dict(), "persistence": 1.02})

        assert "not stationary" in describe_forecast("AAPL", unstable)
        assert "not stationary" not in describe_forecast("AAPL", forecast)
