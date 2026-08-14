"""Pins indicator maths against independently computed references.

Two purposes:

1. Characterisation. Leading-NaN counts and index alignment are locked in, so
   swapping any of these for a library (TA-Lib, pandas-ta) becomes a visible
   diff instead of a silent change in every signal derived from them.
2. Agreement with the standard. ATR and ADX previously used a simple moving
   average, which put them several percent away from TA-Lib, TradingView and
   the Alpha Vantage endpoint this repo also routes ``atr`` to. They now use
   Wilder smoothing and are pinned against it exactly.

The reference values are computed inline from the published definitions, so
these tests add no dependency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.indicator_service import (
    calculate_adx,
    calculate_atr,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_vwap,
)

PERIOD = 14


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    """Deterministic OHLCV series; seeded so failures are reproducible."""
    rng = np.random.default_rng(7)
    n = 120
    close = 100 + np.cumsum(rng.normal(0, 1.5, n))
    spread = np.abs(rng.normal(1.0, 0.4, n))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(1_000, 50_000, n).astype(float),
        }
    )


def _true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    return pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)


# --- correct implementations -------------------------------------------------


def test_rsi_matches_the_wilder_reference(ohlcv):
    """RSI uses Wilder smoothing (alpha = 1/period), as the standard requires."""
    delta = ohlcv["Close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / PERIOD, min_periods=PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / PERIOD, min_periods=PERIOD, adjust=False).mean()
    expected = 100 - (100 / (1 + avg_gain / avg_loss))

    actual = calculate_rsi(ohlcv["Close"], PERIOD)

    pd.testing.assert_series_equal(actual.dropna(), expected.dropna(), check_names=False)


def test_ema_and_macd_match_the_standard_definitions(ohlcv):
    close = ohlcv["Close"]
    expected_ema = close.ewm(span=20, adjust=False).mean()
    pd.testing.assert_series_equal(calculate_ema(close, 20), expected_ema, check_names=False)

    fast = close.ewm(span=12, adjust=False).mean()
    slow = close.ewm(span=26, adjust=False).mean()
    expected_macd = fast - slow
    expected_signal = expected_macd.ewm(span=9, adjust=False).mean()

    macd, signal = calculate_macd(close)
    pd.testing.assert_series_equal(macd, expected_macd, check_names=False)
    pd.testing.assert_series_equal(signal, expected_signal, check_names=False)


def test_vwap_is_volume_weighted_over_the_window(ohlcv):
    typical = (ohlcv["High"] + ohlcv["Low"] + ohlcv["Close"]) / 3
    expected = (typical * ohlcv["Volume"]).rolling(20).sum() / ohlcv["Volume"].rolling(20).sum()

    pd.testing.assert_series_equal(calculate_vwap(ohlcv, 20), expected, check_names=False)


# --- agreement with Wilder ---------------------------------------------------


def _wilder(series: pd.Series) -> pd.Series:
    return series.ewm(alpha=1 / PERIOD, adjust=False, min_periods=PERIOD).mean()


def test_atr_matches_wilder_smoothing_exactly(ohlcv):
    """ATR is a Wilder average of true range, as the standard defines it.

    An SMA here previously put ATR ~4% (worst case ~12%) away from every
    mainstream implementation, which matters because ATR sets stop distances.
    """
    expected = _wilder(_true_range(ohlcv))

    pd.testing.assert_series_equal(calculate_atr(ohlcv, PERIOD), expected, check_names=False)


def test_atr_no_longer_matches_a_simple_average(ohlcv):
    """Guards the fix: an SMA is a materially different series, not a rounding."""
    sma = _true_range(ohlcv).rolling(PERIOD).mean()
    both = pd.DataFrame({"actual": calculate_atr(ohlcv, PERIOD), "sma": sma}).dropna()
    relative_error = ((both["actual"] - both["sma"]).abs() / both["sma"]) * 100

    assert relative_error.max() > 5.0


def test_adx_smooths_every_component_the_wilder_way(ohlcv):
    """Directional movement, true range and DX all use the same smoothing."""
    high, low = ohlcv["High"], ohlcv["Low"]
    up_move = high.diff()
    down_move = low.shift(1) - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = _wilder(_true_range(ohlcv))

    plus_di = 100 * (_wilder(plus_dm) / atr)
    minus_di = 100 * (_wilder(minus_dm) / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    expected = _wilder(dx)

    pd.testing.assert_series_equal(calculate_adx(ohlcv, PERIOD), expected, check_names=False)


# --- warm-up and alignment ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "compute", "first_valid"),
    [
        # RSI warms up one bar earlier than the period suggests: `.diff()`
        # leaves NaN on bar 0, but `.where(delta > 0, 0.0)` rewrites it to 0.0,
        # so the Wilder average sees a full window one bar sooner. The first
        # value therefore includes a synthetic flat bar.
        ("rsi", lambda df: calculate_rsi(df["Close"], PERIOD), PERIOD - 1),
        ("atr", lambda df: calculate_atr(df, PERIOD), PERIOD - 1),
        ("adx", lambda df: calculate_adx(df, PERIOD), PERIOD * 2 - 2),
        ("vwap", lambda df: calculate_vwap(df, 20), 19),
    ],
)
def test_warmup_period_is_pinned(ohlcv, name, compute, first_valid):
    """Leading NaNs are part of the contract.

    ``market_service`` renders them as JSON null and charts skip them, so a
    library swap that shifts the warm-up by even one bar moves every plotted
    point relative to its date.
    """
    series = compute(ohlcv)
    assert series.first_valid_index() == first_valid, name
    assert series.index.equals(ohlcv.index), name


def test_indicators_do_not_reach_into_the_future(ohlcv):
    """Truncating the input must not change earlier values.

    A look-ahead bug here would make a backtest profitable on data the strategy
    could not have had.
    """
    cutoff = 90
    truncated = ohlcv.iloc[:cutoff]

    for compute in (
        lambda df: calculate_rsi(df["Close"], PERIOD),
        lambda df: calculate_atr(df, PERIOD),
        lambda df: calculate_adx(df, PERIOD),
        lambda df: calculate_vwap(df, 20),
    ):
        full = compute(ohlcv).iloc[:cutoff]
        partial = compute(truncated)
        pd.testing.assert_series_equal(full, partial, check_names=False)
