import pandas as pd
import pytest

from backend.services.indicator_service import evaluate_formula_safely


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0, 13.0],
            "High": [11.0, 12.0, 13.0, 14.0],
            "Low": [9.0, 10.0, 11.0, 12.0],
            "Close": [10.5, 11.5, 12.5, 13.5],
            "Volume": [100, 120, 140, 160],
        }
    )


def test_causal_formula_is_allowed():
    result = evaluate_formula_safely(_frame(), "Close - SHIFT(1)")
    assert result.iloc[-1] == pytest.approx(1.0)


@pytest.mark.parametrize("formula", ["Close - SHIFT(1)", "SMA(2)", "RSI(2)", "ATR(2)"])
def test_rolling_warmup_nan_is_not_rejected(formula: str):
    """Every rolling term leads with NaN; rejecting that kills the feature.

    ``market_service`` renders non-finite points as JSON ``null``, so the warm-up
    period is expected downstream and must not fail evaluation.
    """
    result = evaluate_formula_safely(_frame(), formula)
    assert result.isna().any()
    assert result.notna().any()


def test_infinite_result_is_still_rejected():
    with pytest.raises(ValueError):
        evaluate_formula_safely(_frame(), "Close / (Close - Close)")


@pytest.mark.parametrize(
    "formula",
    [
        "SHIFT(-1)",
        "Close.shift(-1)",
        "Close[1]",
        "__import__('os')",
        "SMA(0)",
        "SMA(501)",
    ],
)
def test_future_or_arbitrary_expression_is_rejected(formula: str):
    with pytest.raises(ValueError):
        evaluate_formula_safely(_frame(), formula)
