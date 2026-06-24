"""Unit tests for the screener's deterministic scoring (no network)."""

import numpy as np
import pandas as pd

from backend.services.screener_service import _score_ticker


def _make_df(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame({"Close": closes, "Volume": volumes}, index=idx)


def test_too_little_history_returns_none():
    df = _make_df([100.0] * 30, [1e6] * 30)
    assert _score_ticker("X", df) is None


def test_uptrending_momentum_scores_higher_than_flat():
    n = 120
    up = _make_df(list(np.linspace(100, 130, n)), [1e6] * n)
    flat = _make_df([100.0] * n, [1e6] * n)
    up_score = _score_ticker("UP", up)
    flat_score = _score_ticker("FLAT", flat)
    assert up_score is not None and flat_score is not None
    assert up_score.score > flat_score.score
    assert "uptrend" in up_score.signals


def test_volume_surge_detected():
    n = 120
    volumes = [1e6] * (n - 5) + [3e6] * 5  # 3x surge in the last week
    df = _make_df([100.0 + i * 0.01 for i in range(n)], volumes)
    res = _score_ticker("VOL", df)
    assert res is not None
    assert res.volume_surge > 1.5
    assert "volume_surge" in res.signals


def test_oversold_reversal_candidate():
    n = 120
    # Steady decline producing a washed-out RSI and a >10% monthly drop.
    closes = list(np.linspace(150, 100, n))
    df = _make_df(closes, [1e6] * n)
    res = _score_ticker("DOWN", df)
    assert res is not None
    assert res.rsi_14 < 35
    # Either flagged as oversold_reversal or at least not rewarded as momentum.
    assert "strong_momentum" not in res.signals
