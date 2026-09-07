"""Canonical success semantics for resolved portfolio ratings.

Every learning/calibration path must score the five-tier rating scale the same
way. Absolute directional calls use raw return; relative allocation calls use
benchmark alpha; Hold is neutral around zero alpha when available.
"""

from __future__ import annotations


def finite_return(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def rating_outcome_success(
    rating: object,
    *,
    raw_return: object,
    alpha_return: object,
    hold_band: float = 0.02,
) -> bool | None:
    """Return whether one resolved five-tier rating was successful.

    ``Buy``/``Sell`` are absolute directional calls. ``Overweight`` and
    ``Underweight`` are relative-to-benchmark allocation calls. ``Hold`` means
    roughly neutral performance, preferring alpha when a benchmark is present.
    Missing alpha never silently converts a relative call into an absolute one.
    """
    label = str(rating or "").strip()
    raw = finite_return(raw_return)
    alpha = finite_return(alpha_return)

    if label == "Buy":
        return raw > 0 if raw is not None else None
    if label == "Sell":
        return raw < 0 if raw is not None else None
    if label == "Overweight":
        return alpha > 0 if alpha is not None else None
    if label == "Underweight":
        return alpha < 0 if alpha is not None else None
    if label == "Hold":
        neutral_return = alpha if alpha is not None else raw
        return abs(neutral_return) <= hold_band if neutral_return is not None else None
    return None
