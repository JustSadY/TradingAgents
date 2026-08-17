from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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

    realized_pnl, opening_fee, financing_cost = await _execute_close_position(
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
    assert financing_cost == Decimal("0.0")
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

    realized_pnl, opening_fee, financing_cost = await _execute_close_position(
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
    assert financing_cost == Decimal("0.0")
    assert portfolio.cash_available == Decimal("549.5500")
    assert holding.quantity == Decimal("5")
    assert holding.entry_commission == Decimal("0.5000")


async def test_partial_close_allocates_accrued_financing_pro_rata():
    """Financing follows the closed fraction, and the rest stays on the holding.

    Charging the whole accrued interest on a partial close would double-bill the
    remainder when it is closed later.
    """
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
        interest_accrued=Decimal("2.0000"),
    )

    realized_pnl, opening_fee, financing_cost = await _execute_close_position(
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

    assert financing_cost == Decimal("1.0000")
    assert holding.interest_accrued == Decimal("1.0000")
    # 50 gross - 0.50 entry - 0.55 exit - 1.00 financing
    assert realized_pnl == Decimal("47.9500")
    assert opening_fee == Decimal("0.5000")


def test_mock_trading_does_not_keep_legacy_sqlite_or_persistence_shims() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "mock_trading_service.py").read_text()

    assert "older SQLite development database" not in source
    assert "getattr(holding, \"entry_commission\"" not in source
    assert "from sqlalchemy import delete" not in source
    assert "from sqlalchemy import select" not in source
    assert "IntegrityError" not in source
    assert "select(Portfolio" not in source
    assert "delete(Order" not in source
    assert "delete(Holding" not in source
    assert "Order(" not in source
    assert "Holding(" not in source
    assert "db.add(" not in source
    assert "await db.delete(" not in source
    assert "await db.flush()" not in source
    assert "get_or_create_simulation_portfolio" in source
    assert "lock_portfolio_for_update" in source
    assert "reset_simulation_portfolio" in source
    assert "stage_order" in source
    assert "stage_holding" in source
    assert "delete_holding_row" in source
    assert "flush_portfolio_changes" in source
