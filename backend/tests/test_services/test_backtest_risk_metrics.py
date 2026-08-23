"""Risk-adjusted statistics beside the exact-decimal money metrics.

The money figures stay Decimal because they are money. These ratios are not,
so they come from empyrical — but a ratio that is NaN or infinite must be
reported as absent rather than serialised as a number.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from backend.services.backtest_service import _RISK_METRIC_KEYS, _compute_metrics


def _equity(rows: int = 250, seed: int = 7) -> list[Decimal]:
    rng = np.random.default_rng(seed)
    values = [Decimal("100000")]
    for daily in rng.normal(0.0006, 0.011, rows):
        values.append(values[-1] * Decimal(str(round(1 + daily, 8))))
    return values


_TRADES = [{"pnl": Decimal("120")}, {"pnl": Decimal("-40")}, {"pnl": Decimal("300")}]


def test_every_risk_metric_is_reported_for_a_normal_run():
    metrics = _compute_metrics(_equity(), _TRADES, Decimal("100000"))

    for key in _RISK_METRIC_KEYS:
        assert isinstance(metrics[key], float), key


def test_the_exact_decimal_money_metrics_are_unchanged():
    equity = _equity()
    metrics = _compute_metrics(equity, _TRADES, Decimal("100000"))

    assert metrics["final_value"] == round(float(equity[-1]), 2)
    assert metrics["win_rate"] == pytest.approx(200 / 3, abs=0.01)
    assert metrics["max_drawdown"] <= 0.0


def test_a_run_too_short_to_have_a_distribution_reports_no_risk_metrics():
    metrics = _compute_metrics([Decimal("100000"), Decimal("101000")], [], Decimal("100000"))

    assert all(metrics[key] is None for key in _RISK_METRIC_KEYS)
    assert metrics["total_return"] == pytest.approx(1.0)


def test_a_flat_equity_curve_never_serialises_a_non_finite_ratio():
    """Zero variance makes several of these ratios NaN or infinite."""
    metrics = _compute_metrics([Decimal("100000")] * 120, [], Decimal("100000"))

    for key in _RISK_METRIC_KEYS:
        value = metrics[key]
        assert value is None or np.isfinite(value), key
