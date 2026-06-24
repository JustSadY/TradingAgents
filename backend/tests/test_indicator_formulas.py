"""Tests for the custom chart formula engine (``evaluate_formula_safely``)."""

import numpy as np
import pandas as pd
import pytest

from backend.services.indicator_service import _FORMULA_FUNCS, evaluate_formula_safely


@pytest.fixture
def df():
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, 100))
    spread = np.abs(rng.normal(0.5, 0.2, 100))
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.3, 100),
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": rng.integers(1_000, 50_000, 100).astype(float),
        }
    )


def test_every_registered_function_evaluates(df):
    for name in _FORMULA_FUNCS:
        series = evaluate_formula_safely(df, f"{name}(14)")
        assert len(series) == len(df), name


def test_classic_indicators(df):
    sma = evaluate_formula_safely(df, "SMA(20)")
    assert sma.iloc[-1] == pytest.approx(df["Close"].tail(20).mean())

    stoch = evaluate_formula_safely(df, "(Close - MIN(14)) / (MAX(14) - MIN(14)) * 100")
    assert 0 <= stoch.iloc[-1] <= 100

    roc = evaluate_formula_safely(df, "(Close / SHIFT(10) - 1) * 100")
    expected = (df["Close"].iloc[-1] / df["Close"].iloc[-11] - 1) * 100
    assert roc.iloc[-1] == pytest.approx(expected)


def test_volsma_operates_on_volume_not_close(df):
    volsma = evaluate_formula_safely(df, "VOLSMA(20)")
    assert volsma.iloc[-1] == pytest.approx(df["Volume"].tail(20).mean())
    # The SMA embedded in the VOLSMA name must not be matched separately.
    rel = evaluate_formula_safely(df, "Volume / VOLSMA(20)")
    assert rel.iloc[-1] == pytest.approx(df["Volume"].iloc[-1] / df["Volume"].tail(20).mean())


def test_vwap_stays_within_price_range(df):
    vwap = evaluate_formula_safely(df, "VWAP(20)")
    window_high = df["High"].tail(20).max()
    window_low = df["Low"].tail(20).min()
    assert window_low <= vwap.iloc[-1] <= window_high


def test_atr_is_positive(df):
    atr = evaluate_formula_safely(df, "ATR(14)")
    assert atr.iloc[-1] > 0


def test_case_insensitive_and_whitespace(df):
    a = evaluate_formula_safely(df, "sma( 20 ) / Close")
    b = evaluate_formula_safely(df, "SMA(20)/Close")
    assert a.iloc[-1] == pytest.approx(b.iloc[-1])


def test_invalid_formula_raises_value_error(df):
    with pytest.raises(ValueError, match="could not be calculated"):
        evaluate_formula_safely(df, "FOO(14) ** bar")
