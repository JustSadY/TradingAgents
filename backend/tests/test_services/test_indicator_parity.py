"""Behavioral guardrails around the package-backed indicator implementation.

Exact numerical parity with TA-Lib belongs in
``test_indicator_package_parity.py``.  These tests intentionally cover only
application-level invariants that remain ours: index alignment, warm-up
behavior as exposed by the package, rolling VWAP semantics, and no look-ahead.
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


def test_vwap_is_volume_weighted_over_the_window(ohlcv):
    typical = (ohlcv["High"] + ohlcv["Low"] + ohlcv["Close"]) / 3
    expected = (typical * ohlcv["Volume"]).rolling(20).sum() / ohlcv["Volume"].rolling(20).sum()
    pd.testing.assert_series_equal(calculate_vwap(ohlcv, 20), expected, check_names=False)


@pytest.mark.parametrize(
    "compute",
    [
        lambda df: calculate_rsi(df["Close"], PERIOD),
        lambda df: calculate_atr(df, PERIOD),
        lambda df: calculate_adx(df, PERIOD),
        lambda df: calculate_vwap(df, 20),
        lambda df: calculate_ema(df["Close"], 20),
    ],
)
def test_indicator_index_alignment_is_preserved(ohlcv, compute):
    series = compute(ohlcv)
    assert series.index.equals(ohlcv.index)
    assert series.first_valid_index() is not None


def test_macd_index_alignment_is_preserved(ohlcv):
    macd, signal = calculate_macd(ohlcv["Close"])
    assert macd.index.equals(ohlcv.index)
    assert signal.index.equals(ohlcv.index)


def test_indicators_do_not_reach_into_the_future(ohlcv):
    cutoff = 90
    truncated = ohlcv.iloc[:cutoff]
    for compute in (
        lambda df: calculate_rsi(df["Close"], PERIOD),
        lambda df: calculate_atr(df, PERIOD),
        lambda df: calculate_adx(df, PERIOD),
        lambda df: calculate_vwap(df, 20),
        lambda df: calculate_ema(df["Close"], 20),
    ):
        full = compute(ohlcv).iloc[:cutoff]
        partial = compute(truncated)
        pd.testing.assert_series_equal(full, partial, check_names=False)


def test_macd_does_not_reach_into_the_future(ohlcv):
    cutoff = 90
    full_macd, full_signal = calculate_macd(ohlcv["Close"])
    partial_macd, partial_signal = calculate_macd(ohlcv["Close"].iloc[:cutoff])
    pd.testing.assert_series_equal(full_macd.iloc[:cutoff], partial_macd, check_names=False)
    pd.testing.assert_series_equal(full_signal.iloc[:cutoff], partial_signal, check_names=False)
