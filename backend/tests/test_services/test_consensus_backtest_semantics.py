from types import SimpleNamespace

import pandas as pd

from backend.services.backtest_service import _consensus_target_allocation, _generate_signal


def _analysis(signal: str, target):
    return SimpleNamespace(
        signal=signal,
        portfolio_decision_json={"rating": signal, "position_size_pct": target},
        chart_annotations={},
    )


def _data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Date": pd.Timestamp("2026-01-02"), "Open": 100, "High": 102, "Low": 99, "Close": 101},
            {"Date": pd.Timestamp("2026-01-05"), "Open": 101, "High": 103, "Low": 100, "Close": 102},
        ]
    )


def test_underweight_is_a_reduce_only_consensus_signal() -> None:
    analyses = {"2026-01-02": _analysis("Underweight", 20.0)}

    signal, _stop, _target = _generate_signal(
        _data(),
        _data().iloc[1],
        "consensus",
        analyses,
        consensus_signal_date="2026-01-02",
    )

    assert signal == "UNDERWEIGHT"
    assert _consensus_target_allocation(analyses, "2026-01-02") == 20


def test_zero_target_sell_exits_to_flat_instead_of_opening_short() -> None:
    analyses = {"2026-01-02": _analysis("Sell", 0.0)}

    signal, _stop, _target = _generate_signal(
        _data(),
        _data().iloc[1],
        "consensus",
        analyses,
        consensus_signal_date="2026-01-02",
    )

    assert signal == "EXIT"


def test_positive_target_sell_is_an_explicit_short_intent() -> None:
    analyses = {"2026-01-02": _analysis("Sell", 12.5)}

    signal, _stop, _target = _generate_signal(
        _data(),
        _data().iloc[1],
        "consensus",
        analyses,
        consensus_signal_date="2026-01-02",
    )

    assert signal == "SHORT"
