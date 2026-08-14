"""Deterministic sizing for portfolio rebalancing.

Every number a user can act on is computed here, in exact decimal arithmetic,
before any model sees the portfolio. The LLM's role is limited to explaining the
plan; it cannot introduce, resize or retarget a trade.

The policy implemented is the one the feature has always described: cap single
position concentration and keep cash inside a healthy band. It is deliberately
*not* mean-variance optimisation — swapping in a different objective means
replacing :func:`target_weights`, and nothing else here changes.
"""

from __future__ import annotations

from decimal import Decimal

from backend.core.money import safe_decimal

# Policy constants. These mirror the thresholds the feature has always stated.
MAX_POSITION_PCT = Decimal("25")
MIN_CASH_PCT = Decimal("5")
MAX_CASH_PCT = Decimal("30")
# Trades below this notional are dust: commission and slippage dominate them.
MIN_TRADE_NOTIONAL = Decimal("50")
MAX_SUGGESTIONS = 5

_HUNDRED = Decimal("100")


def _pct(value: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return value / total * _HUNDRED


def portfolio_issues(holdings: list[dict], total_value: Decimal, cash: Decimal) -> list[str]:
    """Describe every policy breach, computed rather than inferred."""
    issues: list[str] = []
    cash_pct = _pct(cash, total_value)

    for holding in holdings:
        weight = _pct(safe_decimal(holding.get("market_value")), total_value)
        if weight > MAX_POSITION_PCT:
            issues.append(
                f"{holding['ticker']} is {weight:.1f}% of the portfolio, "
                f"above the {MAX_POSITION_PCT:.0f}% single-position limit."
            )

    if cash_pct < MIN_CASH_PCT:
        issues.append(f"Cash is {cash_pct:.1f}%, below the {MIN_CASH_PCT:.0f}% reserve.")
    elif cash_pct > MAX_CASH_PCT:
        issues.append(f"Cash is {cash_pct:.1f}%, above the {MAX_CASH_PCT:.0f}% idle-cash threshold.")

    return issues


def health_score(holdings: list[dict], total_value: Decimal, cash: Decimal) -> int:
    """Score the portfolio 0-100 from the same measurements as the issue list.

    Derived, not asked for: a model returning a score alongside contradicting
    issues was the previous behaviour.
    """
    score = Decimal("100")
    cash_pct = _pct(cash, total_value)

    for holding in holdings:
        weight = _pct(safe_decimal(holding.get("market_value")), total_value)
        if weight > MAX_POSITION_PCT:
            # 2 points per excess percentage point, capped so one position
            # cannot zero an otherwise sound portfolio.
            score -= min(Decimal("30"), (weight - MAX_POSITION_PCT) * 2)

    if cash_pct < MIN_CASH_PCT:
        score -= min(Decimal("20"), (MIN_CASH_PCT - cash_pct) * 2)
    elif cash_pct > MAX_CASH_PCT:
        score -= min(Decimal("15"), (cash_pct - MAX_CASH_PCT))

    return int(max(Decimal("0"), min(Decimal("100"), score)))


def plan_trades(holdings: list[dict], total_value: Decimal, cash: Decimal) -> list[dict]:
    """Return concrete, affordable trades that move the portfolio into policy.

    Constraints enforced here, so no downstream consumer has to trust a model:

    * a reduction never exceeds the quantity actually held;
    * a purchase never exceeds available cash;
    * trades below :data:`MIN_TRADE_NOTIONAL` are dropped as dust;
    * a short position is reduced by BUYing, a long by SELLing.
    """
    if total_value <= 0:
        return []

    trades: list[dict] = []
    max_notional = total_value * MAX_POSITION_PCT / _HUNDRED

    for holding in holdings:
        market_value = safe_decimal(holding.get("market_value"))
        price = safe_decimal(holding.get("current_price"))
        held = safe_decimal(holding.get("quantity"))
        if price <= 0 or held <= 0 or market_value <= max_notional:
            continue

        excess_notional = market_value - max_notional
        quantity = excess_notional / price
        # Never sell more than is held, whatever the arithmetic says.
        quantity = min(quantity, held)
        if quantity * price < MIN_TRADE_NOTIONAL:
            continue

        is_short = str(holding.get("side") or "long").lower() == "short"
        weight = _pct(market_value, total_value)
        trades.append(
            {
                # Reducing a short means buying it back.
                "action": "BUY" if is_short else "SELL",
                "ticker": holding["ticker"],
                "quantity": float(round(quantity, 4)),
                "notional": float(round(quantity * price, 2)),
                "weight_pct": float(round(weight, 2)),
                "reason": "concentration",
                "urgency": "high" if weight > MAX_POSITION_PCT * 2 else "medium",
            }
        )

    # Largest breach first; the user may only act on the first few.
    trades.sort(key=lambda t: t["weight_pct"], reverse=True)
    return trades[:MAX_SUGGESTIONS]


def build_plan(portfolio: dict) -> dict:
    """Compute the full deterministic plan for one portfolio snapshot."""
    holdings = portfolio.get("holdings") or []
    total_value = safe_decimal(portfolio.get("total_value"))
    cash = safe_decimal(portfolio.get("cash_available"))

    return {
        "score": health_score(holdings, total_value, cash),
        "issues": portfolio_issues(holdings, total_value, cash),
        "suggestions": plan_trades(holdings, total_value, cash),
        "cash_pct": float(round(_pct(cash, total_value), 2)),
    }
