"""Portfolio-level risk guards applied before a leveraged order is placed.

Per-trade sizing (Kelly, risk-per-trade) already lives in
``trading_orchestrator``; this module adds the *portfolio-wide* checks that only
make sense once leverage exists:

- **Single-name concentration:** no one ticker's notional may exceed
  ``max_concentration_pct`` of account equity.
- **Gross exposure:** the sum of all leveraged position notionals may not exceed
  ``max_gross_exposure`` × equity (caps total portfolio leverage).

Both are pure functions over already-known numbers (no market data fetch), so
they're cheap and unit-testable. ``cap_order_notional`` returns the largest
notional the new order may take without breaching either limit (0 → skip).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_CONCENTRATION_PCT = 25.0  # max % of equity in a single ticker
DEFAULT_MAX_GROSS_EXPOSURE = 3.0  # max sum(notional) / equity across positions


@dataclass
class RiskAssessment:
    allowed_notional: float
    capped: bool
    reason: str = ""


def cap_order_notional(
    *,
    equity: float,
    proposed_notional: float,
    existing_ticker_notional: float,
    existing_gross_notional: float,
    max_concentration_pct: float = DEFAULT_MAX_CONCENTRATION_PCT,
    max_gross_exposure: float = DEFAULT_MAX_GROSS_EXPOSURE,
) -> RiskAssessment:
    """Return how much of ``proposed_notional`` may be added without breaching
    the concentration or gross-exposure limits.

    - ``equity``: current account equity (cash + position equity).
    - ``existing_ticker_notional``: notional already held in this ticker.
    - ``existing_gross_notional``: sum of notional across all current positions.
    """
    if equity <= 0 or proposed_notional <= 0:
        return RiskAssessment(allowed_notional=0.0, capped=proposed_notional > 0, reason="no_equity")

    # Headroom under the single-name concentration cap.
    conc_ceiling = (max_concentration_pct / 100.0) * equity
    conc_headroom = max(0.0, conc_ceiling - existing_ticker_notional)

    # Headroom under the gross-exposure cap.
    gross_ceiling = max_gross_exposure * equity
    gross_headroom = max(0.0, gross_ceiling - existing_gross_notional)

    allowed = min(proposed_notional, conc_headroom, gross_headroom)
    if allowed >= proposed_notional:
        return RiskAssessment(allowed_notional=proposed_notional, capped=False)

    reason = "concentration" if conc_headroom <= gross_headroom else "gross_exposure"
    return RiskAssessment(allowed_notional=max(0.0, allowed), capped=True, reason=reason)
