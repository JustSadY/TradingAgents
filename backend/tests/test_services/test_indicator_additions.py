"""The standard indicators added beside the original six.

RSI, MACD, EMA, ADX, ATR and rolling VWAP already had wrappers; SMA, Bollinger
Bands, the stochastic, CCI, MFI and Williams %R did not, so the custom formula
language and every caller could only reach a third of what the production
indicator engine provides.

Numerical parity with TA-Lib is asserted here for the same reason
``test_indicator_package_parity.py`` asserts it for the originals: these are
thin adapters, and the only thing that can silently break them is a
parameter-order change in the package.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import talib

from backend.services.indicator_service import (
    calculate_bbands,
    calculate_cci,
    calculate_mfi,
    calculate_sma,
    calculate_stoch,
    calculate_willr,
    evaluate_formula_safely,
)


def _array(series: pd.Series) -> np.ndarray:
    return np.ascontiguousarray(series.to_numpy(dtype="float64"))


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = 300
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + rng.uniform(0.1, 2.0, rows),
            "Low": close - rng.uniform(0.1, 2.0, rows),
            "Close": close,
            "Volume": rng.integers(10_000, 500_000, rows).astype(float),
        }
    )


class TestPackageParity:
    def test_sma_matches_the_package(self, ohlcv):
        close = ohlcv["Close"].astype(float)
        pd.testing.assert_series_equal(
            calculate_sma(close, 20),
            pd.Series(talib.SMA(_array(close), timeperiod=20), index=ohlcv.index, dtype="float64", name="SMA_20"),
        )

    def test_bollinger_bands_match_the_package(self, ohlcv):
        close = ohlcv["Close"].astype(float)
        direct_upper, direct_middle, direct_lower = talib.BBANDS(
            _array(close), timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=talib.MA_Type.SMA
        )
        lower, middle, upper = calculate_bbands(close, 20)

        for produced, direct, name in (
            (lower, direct_lower, "BBL_20_2.0"),
            (middle, direct_middle, "BBM_20_2.0"),
            (upper, direct_upper, "BBU_20_2.0"),
        ):
            pd.testing.assert_series_equal(
                produced,
                pd.Series(direct, index=ohlcv.index, dtype="float64", name=name),
            )

    def test_stochastic_matches_the_package(self, ohlcv):
        direct_k, direct_d = talib.STOCH(
            _array(ohlcv["High"]),
            _array(ohlcv["Low"]),
            _array(ohlcv["Close"]),
            fastk_period=14,
            slowk_period=3,
            slowk_matype=talib.MA_Type.SMA,
            slowd_period=3,
            slowd_matype=talib.MA_Type.SMA,
        )
        k_line, d_line = calculate_stoch(ohlcv)

        for produced, direct, name in (
            (k_line, direct_k, "STOCHk_14_3_3"),
            (d_line, direct_d, "STOCHd_14_3_3"),
        ):
            pd.testing.assert_series_equal(
                produced,
                pd.Series(direct, index=ohlcv.index, dtype="float64", name=name),
            )

    def test_single_series_indicators_match_the_package(self, ohlcv):
        high, low = ohlcv["High"].astype(float), ohlcv["Low"].astype(float)
        close, volume = ohlcv["Close"].astype(float), ohlcv["Volume"].astype(float)

        high_a, low_a, close_a, volume_a = (_array(s) for s in (high, low, close, volume))
        cases = [
            (calculate_cci(ohlcv, 20), talib.CCI(high_a, low_a, close_a, timeperiod=20), "CCI_20"),
            (calculate_mfi(ohlcv, 14), talib.MFI(high_a, low_a, close_a, volume_a, timeperiod=14), "MFI_14"),
            (calculate_willr(ohlcv, 14), talib.WILLR(high_a, low_a, close_a, timeperiod=14), "WILLR_14"),
        ]
        for produced, expected, name in cases:
            pd.testing.assert_series_equal(
                produced,
                pd.Series(expected, index=ohlcv.index, dtype="float64", name=name),
            )


class TestApplicationInvariants:
    @pytest.mark.parametrize(
        "compute",
        [
            lambda df: calculate_sma(df["Close"], 20),
            lambda df: calculate_cci(df, 20),
            lambda df: calculate_mfi(df, 14),
            lambda df: calculate_willr(df, 14),
            lambda df: calculate_bbands(df["Close"], 20)[2],
            lambda df: calculate_stoch(df)[0],
        ],
    )
    def test_index_alignment_and_dtype_are_preserved(self, ohlcv, compute):
        result = compute(ohlcv)
        assert isinstance(result, pd.Series)
        assert result.dtype == "float64"
        pd.testing.assert_index_equal(result.index, ohlcv.index)

    @pytest.mark.parametrize(
        "compute",
        [
            lambda df: calculate_sma(df["Close"], 20),
            lambda df: calculate_cci(df, 20),
            lambda df: calculate_mfi(df, 14),
            lambda df: calculate_willr(df, 14),
            lambda df: calculate_bbands(df["Close"], 20)[2],
            lambda df: calculate_stoch(df)[0],
        ],
    )
    def test_no_look_ahead(self, ohlcv, compute):
        """A later bar must not change an earlier value."""
        cutoff = 200
        full = compute(ohlcv).iloc[:cutoff]
        truncated = compute(ohlcv.iloc[:cutoff].copy())
        pd.testing.assert_series_equal(full, truncated, check_names=False)

    def test_bollinger_bands_are_ordered(self, ohlcv):
        lower, middle, upper = calculate_bbands(ohlcv["Close"], 20)
        warm = slice(25, None)
        assert (lower[warm] <= middle[warm]).all()
        assert (middle[warm] <= upper[warm]).all()

    def test_bounded_oscillators_stay_in_range(self, ohlcv):
        k_line, _ = calculate_stoch(ohlcv)
        assert k_line.dropna().between(0, 100).all()
        assert calculate_mfi(ohlcv, 14).dropna().between(0, 100).all()
        assert calculate_willr(ohlcv, 14).dropna().between(-100, 0).all()

    def test_an_empty_frame_yields_empty_series_rather_than_raising(self):
        empty = pd.DataFrame({c: pd.Series(dtype="float64") for c in ("Open", "High", "Low", "Close", "Volume")})
        lower, middle, upper = calculate_bbands(empty["Close"], 20)
        k_line, d_line = calculate_stoch(empty)
        for series in (lower, middle, upper, k_line, d_line):
            assert series.empty


class TestFormulaLanguage:
    """The new indicators are reachable from user-authored custom formulas."""

    @pytest.mark.parametrize(
        "formula",
        [
            "CCI(20)",
            "MFI(14)",
            "WILLR(14)",
            "BBU(20) - BBL(20)",
            "STOCHK(14)",
            "STOCHD(14)",
            "(Close - BBL(20)) / (BBU(20) - BBL(20))",
        ],
    )
    def test_new_symbols_evaluate(self, ohlcv, formula):
        result = evaluate_formula_safely(ohlcv, formula)
        assert isinstance(result, pd.Series)
        assert result.notna().any()

    def test_sma_still_resolves_and_now_uses_the_package(self, ohlcv):
        pd.testing.assert_series_equal(
            evaluate_formula_safely(ohlcv, "SMA(20)"),
            calculate_sma(ohlcv["Close"], 20),
            check_names=False,
        )

    def test_volsma_is_not_shadowed_by_the_sma_symbol(self, ohlcv):
        """`\\bSMA(` must not match inside `VOLSMA(`."""
        pd.testing.assert_series_equal(
            evaluate_formula_safely(ohlcv, "VOLSMA(20)"),
            ohlcv["Volume"].rolling(20).mean(),
            check_names=False,
        )

    def test_obv_is_not_exposed_to_the_formula_language(self, ohlcv):
        """It is cumulative and takes no period, so `OBV(n)` has no meaning."""
        with pytest.raises(ValueError):
            evaluate_formula_safely(ohlcv, "OBV(20)")
