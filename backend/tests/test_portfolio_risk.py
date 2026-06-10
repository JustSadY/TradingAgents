"""Unit tests for the portfolio-level risk guard (concentration + gross exposure)."""

from backend.services.portfolio_risk_service import cap_order_notional


def test_order_allowed_when_within_limits():
    a = cap_order_notional(
        equity=100_000,
        proposed_notional=10_000,
        existing_ticker_notional=0,
        existing_gross_notional=0,
    )
    assert not a.capped
    assert a.allowed_notional == 10_000


def test_concentration_cap_limits_single_name():
    # 25% cap on $100k equity = $25k ceiling; already hold $20k of this name.
    a = cap_order_notional(
        equity=100_000,
        proposed_notional=10_000,
        existing_ticker_notional=20_000,
        existing_gross_notional=20_000,
        max_concentration_pct=25.0,
    )
    assert a.capped
    assert a.reason == "concentration"
    assert a.allowed_notional == 5_000  # only $5k headroom to the $25k cap


def test_gross_exposure_cap_limits_total_leverage():
    # 3x gross cap on $100k equity = $300k ceiling; already $290k gross.
    a = cap_order_notional(
        equity=100_000,
        proposed_notional=50_000,
        existing_ticker_notional=0,
        existing_gross_notional=290_000,
        max_concentration_pct=100.0,  # concentration not binding here
        max_gross_exposure=3.0,
    )
    assert a.capped
    assert a.reason == "gross_exposure"
    assert a.allowed_notional == 10_000  # only $10k headroom to the $300k cap


def test_no_equity_blocks_order():
    a = cap_order_notional(
        equity=0,
        proposed_notional=10_000,
        existing_ticker_notional=0,
        existing_gross_notional=0,
    )
    assert a.capped
    assert a.allowed_notional == 0.0


def test_fully_concentrated_leaves_no_room():
    a = cap_order_notional(
        equity=100_000,
        proposed_notional=10_000,
        existing_ticker_notional=25_000,  # already at the 25% cap
        existing_gross_notional=25_000,
        max_concentration_pct=25.0,
    )
    assert a.capped
    assert a.allowed_notional == 0.0
