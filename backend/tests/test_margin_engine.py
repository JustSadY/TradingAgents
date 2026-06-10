"""Unit tests for the pure margin/leverage math."""

from decimal import Decimal

from backend.services.margin_engine import (
    accrue_interest,
    clamp_leverage,
    is_liquidatable_long,
    liquidation_price_long,
    maintenance_rate_for_leverage,
    margin_required,
    position_equity_long,
)


def test_clamp_leverage_bounds():
    assert clamp_leverage(0.5) == Decimal("1")
    assert clamp_leverage(1) == Decimal("1")
    assert clamp_leverage(3) == Decimal("3")
    assert clamp_leverage(50) == Decimal("10")  # capped at max
    assert clamp_leverage(float("nan")) == Decimal("1")
    assert clamp_leverage("not-a-number") == Decimal("1")


def test_margin_required():
    # $10,000 notional at 5x → $2,000 equity posted.
    assert margin_required(Decimal("10000"), Decimal("5")) == Decimal("2000")
    # Spot (1x) requires the full notional.
    assert margin_required(Decimal("10000"), Decimal("1")) == Decimal("10000")


def test_liquidation_price_spot_is_zero():
    # Nothing borrowed → a spot long can never be liquidated.
    assert liquidation_price_long(Decimal("100"), Decimal("0"), Decimal("0.1")) == Decimal("0")


def test_maintenance_rate_below_initial_margin():
    # Maintenance rate must stay below the initial margin (1/leverage) so a
    # freshly opened position is never instantly liquidatable.
    for lev in (Decimal("2"), Decimal("5"), Decimal("10")):
        initial_margin = Decimal("1") / lev
        assert maintenance_rate_for_leverage(lev) < initial_margin
    # Spot (1x) has no maintenance requirement.
    assert maintenance_rate_for_leverage(Decimal("1")) == Decimal("0")


def test_leveraged_long_liquidation_below_entry():
    # 5x long at $100: liquidation must be below the $100 entry.
    entry = Decimal("100")
    qty = Decimal("100")
    borrowed = qty * entry * (Decimal("1") - Decimal("1") / Decimal("5"))  # 8000
    m = maintenance_rate_for_leverage(Decimal("5"))
    liq = liquidation_price_long(qty, borrowed, m)
    assert liq < entry


def test_liquidation_price_long_formula():
    # 100 shares, $8,000 borrowed, 25% maintenance.
    # liq = borrowed / (qty * (1 - mr)) = 8000 / (100 * 0.75) = 106.666...
    liq = liquidation_price_long(Decimal("100"), Decimal("8000"), Decimal("0.25"))
    assert liq == Decimal("8000") / (Decimal("100") * Decimal("0.75"))
    # At the liquidation price, equity equals the maintenance requirement.
    equity = position_equity_long(Decimal("100"), liq, Decimal("8000"))
    maintenance = Decimal("0.25") * Decimal("100") * liq
    assert abs(equity - maintenance) < Decimal("0.0001")


def test_is_liquidatable_long():
    assert is_liquidatable_long(Decimal("105"), Decimal("106")) is True
    assert is_liquidatable_long(Decimal("107"), Decimal("106")) is False
    assert is_liquidatable_long(Decimal("50"), Decimal("0")) is False  # no leverage


def test_accrue_interest_pro_rata():
    # $10,000 borrowed at 8% APR for exactly one year.
    year = Decimal(str(365 * 24 * 60 * 60))
    interest = accrue_interest(Decimal("10000"), year, Decimal("0.08"))
    assert abs(interest - Decimal("800")) < Decimal("0.01")
    # Half a year → half the interest.
    half = accrue_interest(Decimal("10000"), year / 2, Decimal("0.08"))
    assert abs(half - Decimal("400")) < Decimal("0.01")
    # Nothing borrowed → no interest.
    assert accrue_interest(Decimal("0"), year) == Decimal("0")


def test_higher_borrowing_raises_liquidation_price():
    # Same maintenance rate; more borrowed → closer (higher) liquidation price.
    low = liquidation_price_long(Decimal("100"), Decimal("5000"), Decimal("0.1"))
    high = liquidation_price_long(Decimal("100"), Decimal("9000"), Decimal("0.1"))
    assert high > low
