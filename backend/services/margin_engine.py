"""Pure margin / leverage math for the paper-trading engine.

These functions are deliberately side-effect free (Decimal in, Decimal out) so
they can be unit-tested without a database. The stateful order flow in
``mock_trading_service`` calls into them.

Model (leveraged *long* positions — the direction the AI signals trade):

- Opening ``qty`` shares at ``price`` with leverage ``L``:
    notional        = qty * price
    margin_required = notional / L           (equity the trader puts up)
    borrowed        = notional - margin       (broker loan funding the rest)
  Cash decreases by ``margin_required + commission``; the broker funds
  ``borrowed``. A spot trade is just ``L = 1`` → ``borrowed = 0``.

- Position equity at price ``p``:  ``qty * p - borrowed``.

- Maintenance margin: the position is liquidated when its equity falls to
  ``maintenance_rate * notional_now``. Solving for the long liquidation price:
    qty*p - borrowed <= mr * qty*p
    p <= borrowed / (qty * (1 - mr))

- Closing repays the borrowed principal first; the remainder (original margin
  ± P&L, minus interest and commission) returns to cash.

- Borrowed funds accrue simple interest at an annual rate, pro-rated by the
  fraction of a year the funds were outstanding.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Sensible defaults; overridable per call from runtime config.
DEFAULT_MAX_LEVERAGE = Decimal("10")
DEFAULT_ANNUAL_INTEREST_RATE = Decimal("0.08")  # 8% APR on borrowed funds
# Maintenance margin as a fraction of the *initial* margin (1/leverage). It must
# be strictly below the initial margin, otherwise a position would be
# liquidatable the instant it opens. 0.5 → liquidation buffer is half the posted
# margin (e.g. 5x has 20% initial margin, 10% maintenance).
DEFAULT_MAINTENANCE_FRACTION = Decimal("0.5")
_SECONDS_PER_YEAR = Decimal(str(365 * 24 * 60 * 60))


def maintenance_rate_for_leverage(
    leverage: Decimal, fraction: Decimal = DEFAULT_MAINTENANCE_FRACTION
) -> Decimal:
    """Maintenance margin rate (as a fraction of notional) for a leverage level.

    Derived from the initial margin (1/leverage) so it is always lower than it,
    guaranteeing a freshly opened position is not immediately liquidatable.
    Returns 0 for spot (1x) positions, which can never be liquidated.
    """
    if leverage <= 1:
        return Decimal("0")
    return (Decimal("1") / leverage) * fraction


def clamp_leverage(leverage, max_leverage: Decimal = DEFAULT_MAX_LEVERAGE) -> Decimal:
    """Coerce an arbitrary leverage value into the valid ``[1, max]`` range."""
    try:
        lev = Decimal(str(leverage))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal("1")
    if not lev.is_finite() or lev < Decimal("1"):
        return Decimal("1")
    return min(lev, max_leverage)


def margin_required(notional: Decimal, leverage: Decimal) -> Decimal:
    """Equity the trader must post to open ``notional`` exposure at ``leverage``."""
    if leverage <= 0:
        leverage = Decimal("1")
    return notional / leverage


def liquidation_price_long(
    quantity: Decimal,
    borrowed: Decimal,
    maintenance_rate: Decimal,
) -> Decimal:
    """Price at which a leveraged long is force-closed.

    Liquidation triggers when position equity falls to ``maintenance_rate`` of
    the (current) notional:  qty*p - borrowed = maintenance_rate * qty*p, so
    ``p = borrowed / (qty * (1 - maintenance_rate))``.

    Returns 0 when nothing is borrowed (a spot long can never be liquidated).
    """
    if quantity <= 0 or borrowed <= 0 or maintenance_rate >= 1:
        return Decimal("0")
    denom = quantity * (Decimal("1") - maintenance_rate)
    if denom <= 0:
        return Decimal("0")
    return borrowed / denom


def position_equity_long(quantity: Decimal, price: Decimal, borrowed: Decimal) -> Decimal:
    """Trader's equity in a long position at the given mark price."""
    return quantity * price - borrowed


def accrue_interest(
    borrowed: Decimal,
    elapsed_seconds: Decimal,
    annual_rate: Decimal = DEFAULT_ANNUAL_INTEREST_RATE,
) -> Decimal:
    """Simple interest owed on ``borrowed`` over ``elapsed_seconds``."""
    if borrowed <= 0 or elapsed_seconds <= 0:
        return Decimal("0")
    return borrowed * annual_rate * (elapsed_seconds / _SECONDS_PER_YEAR)


def is_liquidatable_long(price: Decimal, liquidation_price: Decimal) -> bool:
    """True when a long's mark price has reached/breached its liquidation level."""
    return liquidation_price > 0 and price <= liquidation_price
