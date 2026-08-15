from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta_classic as ta

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


def test_standard_indicators_are_pandas_ta_classic_results():
    frame = _ohlcv()
    close = frame["Close"].astype(float)

    pd.testing.assert_series_equal(
        calculate_ema(close, 20),
        pd.Series(ta.ema(close, length=20, talib=False), index=frame.index, dtype="float64", name="EMA_20"),
    )
    pd.testing.assert_series_equal(
        calculate_rsi(close, 14),
        pd.Series(ta.rsi(close, length=14, talib=False), index=frame.index, dtype="float64", name="RSI_14"),
    )

    macd, signal = calculate_macd(close)
    direct_macd = ta.macd(close, fast=12, slow=26, signal=9, talib=False)
    macd_col = next(c for c in direct_macd.columns if c.startswith("MACD_"))
    signal_col = next(c for c in direct_macd.columns if c.startswith("MACDs_"))
    pd.testing.assert_series_equal(macd, pd.Series(direct_macd[macd_col], index=frame.index, dtype="float64", name=macd_col))
    pd.testing.assert_series_equal(signal, pd.Series(direct_macd[signal_col], index=frame.index, dtype="float64", name=signal_col))

    direct_adx = ta.adx(frame["High"], frame["Low"], close, length=14)
    adx_col = next(c for c in direct_adx.columns if c.startswith("ADX_"))
    pd.testing.assert_series_equal(
        calculate_adx(frame, 14),
        pd.Series(direct_adx[adx_col], index=frame.index, dtype="float64", name=adx_col),
    )

    pd.testing.assert_series_equal(
        calculate_atr(frame, 14),
        pd.Series(ta.atr(frame["High"], frame["Low"], close, length=14, talib=False), index=frame.index, dtype="float64", name="ATR_14"),
    )

    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3.0
    pd.testing.assert_series_equal(
        calculate_vwap(frame, 14),
        pd.Series(ta.vwma(typical, frame["Volume"].astype(float), length=14), index=frame.index, dtype="float64", name="VWAP_14"),
    )
