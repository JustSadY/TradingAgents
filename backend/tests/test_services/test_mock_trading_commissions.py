from __future__ import annotations

from decimal import Decimal

from backend.models.portfolio import Holding, Portfolio
from backend.services.mock_trading_service import _execute_close_position

def _portfolio() -> Portfolio:
    return Portfolio(
        id=1,
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("10000"),
        current_balance=Decimal("10000"),
        cash_available=Decimal("0"),
        margin_used=Decimal("1000"),
    )

async def test_partial_long_close_reports_and_allocates_opening_commission():
    portfolio = _portfolio()
    holding = Holding(
        portfolio_id=1,
        ticker="AAPL",
        quantity=Decimal("10"),
        avg_buy_price=Decimal("100"),
        current_price=Decimal("100"),
        side="long",
        leverage=Decimal("1"),
        margin_used=Decimal("1000"),
        borrowed_amount=Decimal("0"),
        entry_commission=Decimal("1.0000"),
    )

    realized_pnl, opening_fee = await _execute_close_position(
        object(),
        portfolio,
        holding,
        Decimal("110"),
        Decimal("5"),
        Decimal("550"),
        Decimal("0.5500"),
        "long",
        "en",
        5.0,
    )

    assert realized_pnl == Decimal("48.9500")
    assert opening_fee == Decimal("0.5000")
    assert portfolio.cash_available == Decimal("549.4500")
    assert holding.quantity == Decimal("5")
    assert holding.entry_commission == Decimal("0.5000")

async def test_partial_short_close_does_not_double_debit_opening_commission():
    portfolio = _portfolio()
    holding = Holding(
        portfolio_id=1,
        ticker="TSLA",
        quantity=Decimal("10"),
        avg_buy_price=Decimal("100"),
        current_price=Decimal("100"),
        side="short",
        leverage=Decimal("1"),
        margin_used=Decimal("1000"),
        borrowed_amount=Decimal("1000"),
        entry_commission=Decimal("1.0000"),
    )

    realized_pnl, opening_fee = await _execute_close_position(
        object(),
        portfolio,
        holding,
        Decimal("90"),
        Decimal("5"),
        Decimal("450"),
        Decimal("0.4500"),
        "short",
        "en",
        5.0,
    )

    assert realized_pnl == Decimal("49.0500")
    assert opening_fee == Decimal("0.5000")
    assert portfolio.cash_available == Decimal("549.5500")
    assert holding.quantity == Decimal("5")
    assert holding.entry_commission == Decimal("0.5000")
