"""The standard indicators added beside the original six.

RSI, MACD, EMA, ADX, ATR and rolling VWAP already had wrappers; SMA, Bollinger
Bands, the stochastic, CCI, MFI, Williams %R and OBV did not, so the custom
formula language and every caller could only reach a third of what the
production indicator engine provides.

Numerical parity with pandas-ta-classic is asserted here for the same reason
``test_indicator_package_parity.py`` asserts it for the originals: these are
thin adapters, and the only thing that can silently break them is a column-name
or parameter-order change in the package.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta
import pytest

from backend.services.indicator_service import (
    calculate_bbands,
    calculate_cci,
    calculate_mfi,
    calculate_sma,
    calculate_stoch,
    calculate_willr,
    evaluate_formula_safely,
)


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
            pd.Series(ta.sma(close, length=20, talib=False), index=ohlcv.index, dtype="float64", name="SMA_20"),
        )

    def test_bollinger_bands_match_the_package(self, ohlcv):
        close = ohlcv["Close"].astype(float)
        direct = ta.bbands(close, length=20, std=2.0, talib=False)
        lower, middle, upper = calculate_bbands(close, 20)

        for produced, prefix in ((lower, "BBL_"), (middle, "BBM_"), (upper, "BBU_")):
            column = next(c for c in direct.columns if str(c).startswith(prefix))
            pd.testing.assert_series_equal(
                produced,
                pd.Series(direct[column], index=ohlcv.index, dtype="float64", name=column),
            )

    def test_stochastic_matches_the_package(self, ohlcv):
        direct = ta.stoch(
            ohlcv["High"].astype(float),
            ohlcv["Low"].astype(float),
            ohlcv["Close"].astype(float),
            k=14,
            d=3,
            smooth_k=3,
            talib=False,
        )
        k_line, d_line = calculate_stoch(ohlcv)

        for produced, prefix in ((k_line, "STOCHk_"), (d_line, "STOCHd_")):
            column = next(c for c in direct.columns if str(c).startswith(prefix))
            pd.testing.assert_series_equal(
                produced,
                pd.Series(direct[column], index=ohlcv.index, dtype="float64", name=column),
            )

    def test_single_series_indicators_match_the_package(self, ohlcv):
        high, low = ohlcv["High"].astype(float), ohlcv["Low"].astype(float)
        close, volume = ohlcv["Close"].astype(float), ohlcv["Volume"].astype(float)

        cases = [
            (calculate_cci(ohlcv, 20), ta.cci(high, low, close, length=20, talib=False), "CCI_20"),
            (calculate_mfi(ohlcv, 14), ta.mfi(high, low, close, volume, length=14, talib=False), "MFI_14"),
            (calculate_willr(ohlcv, 14), ta.willr(high, low, close, length=14, talib=False), "WILLR_14"),
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
