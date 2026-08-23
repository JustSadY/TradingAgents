from __future__ import annotations

import numpy as np
import pandas as pd
import talib

from backend.services.indicator_service import (
    calculate_adx,
    calculate_atr,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_vwap,
)


def _ohlcv(rows: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    high = close + rng.uniform(0.1, 2.0, rows)
    low = close - rng.uniform(0.1, 2.0, rows)
    volume = rng.integers(10_000, 500_000, rows)
    return pd.DataFrame({"High": high, "Low": low, "Close": close, "Volume": volume})


def _array(frame: pd.DataFrame, column: str) -> np.ndarray:
    return np.ascontiguousarray(frame[column].to_numpy(dtype="float64"))


def test_standard_indicators_are_talib_results():
    frame = _ohlcv()
    close = frame["Close"].astype(float)
    high_a, low_a, close_a = (_array(frame, c) for c in ("High", "Low", "Close"))

    pd.testing.assert_series_equal(
        calculate_ema(close, 20),
        pd.Series(talib.EMA(close_a, timeperiod=20), index=frame.index, dtype="float64", name="EMA_20"),
    )
    pd.testing.assert_series_equal(
        calculate_rsi(close, 14),
        pd.Series(talib.RSI(close_a, timeperiod=14), index=frame.index, dtype="float64", name="RSI_14"),
    )

    macd, signal = calculate_macd(close)
    direct_macd, direct_signal, _ = talib.MACD(close_a, fastperiod=12, slowperiod=26, signalperiod=9)
    pd.testing.assert_series_equal(
        macd, pd.Series(direct_macd, index=frame.index, dtype="float64", name="MACD_12_26_9")
    )
    pd.testing.assert_series_equal(
        signal, pd.Series(direct_signal, index=frame.index, dtype="float64", name="MACDs_12_26_9")
    )

    pd.testing.assert_series_equal(
        calculate_adx(frame, 14),
        pd.Series(
            talib.ADX(high_a, low_a, close_a, timeperiod=14), index=frame.index, dtype="float64", name="ADX_14"
        ),
    )
    pd.testing.assert_series_equal(
        calculate_atr(frame, 14),
        pd.Series(
            talib.ATR(high_a, low_a, close_a, timeperiod=14), index=frame.index, dtype="float64", name="ATR_14"
        ),
    )

    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3.0
    volume = frame["Volume"].astype(float)
    expected_vwap = (typical * volume).rolling(window=14).sum() / volume.rolling(window=14).sum()
    pd.testing.assert_series_equal(
        calculate_vwap(frame, 14),
        pd.Series(expected_vwap, index=frame.index, dtype="float64", name="VWAP_14"),
    )
