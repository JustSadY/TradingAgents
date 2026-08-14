from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services.indicator_service import calculate_adx, calculate_atr, calculate_macd, calculate_rsi, calculate_vwap
from backend.services.research_integrations import talib_standard_indicators


def _ohlcv(rows: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, rows))
    high = close + rng.uniform(0.1, 2.0, rows)
    low = close - rng.uniform(0.1, 2.0, rows)
    volume = rng.integers(10_000, 500_000, rows)
    return pd.DataFrame({"High": high, "Low": low, "Close": close, "Volume": volume})


def test_talib_standard_indicator_parity_when_installed():
    pytest.importorskip("talib")
    frame = _ohlcv()
    reference = talib_standard_indicators(frame, period=14)
    native_macd, native_signal = calculate_macd(frame["Close"])

    # The native implementation intentionally has a different warm-up seed;
    # after a generous burn-in the two standard definitions must converge.
    tail = slice(180, None)
    comparisons = {
        "rsi": (calculate_rsi(frame["Close"], 14), reference["rsi"], 0.25),
        "macd": (native_macd, reference["macd"], 0.05),
        "macd_signal": (native_signal, reference["macd_signal"], 0.05),
        "adx": (calculate_adx(frame, 14), reference["adx"], 0.5),
        "atr": (calculate_atr(frame, 14), reference["atr"], 0.05),
        "vwap": (calculate_vwap(frame, 14), reference["vwap"], 1e-10),
    }
    for name, (native, external, tolerance) in comparisons.items():
        delta = (native.iloc[tail] - external.iloc[tail]).abs().dropna()
        assert not delta.empty, name
        assert float(delta.median()) <= tolerance, f"{name} median delta={float(delta.median())}"
