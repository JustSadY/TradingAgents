from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Holding, Portfolio
from backend.models.user import User
from backend.repositories.portfolio import (
    get_or_create_simulation_portfolio,
    get_portfolio_by_id,
    list_simulation_portfolios_for_update,
)


class _Result:
    def __init__(self, row) -> None:
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _ExistingPortfolioSession:
    def __init__(self, row) -> None:
        self.row = row
        self.execute_calls = 0

    async def execute(self, _statement):
        self.execute_calls += 1
        return _Result(self.row)

    async def refresh(self, *_args, **_kwargs):  # pragma: no cover - failure guard
        raise AssertionError("existing eager-loaded portfolio must not be refreshed")


async def test_get_or_create_existing_portfolio_does_not_refresh_holdings() -> None:
    portfolio = SimpleNamespace(id=17, holdings=[SimpleNamespace(ticker="AAPL")])
    db = _ExistingPortfolioSession(portfolio)

    result = await get_or_create_simulation_portfolio(
        db,
        user_id=7,
        initial_capital=100_000,
    )

    assert result is portfolio
    assert result.holdings[0].ticker == "AAPL"
    assert db.execute_calls == 1


async def test_monitor_preload_is_reused_without_followup_select(
    db: AsyncSession,
    test_user: User,
) -> None:
    portfolio = Portfolio(
        user_id=test_user.id,
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("100000"),
        current_balance=Decimal("100000"),
        cash_available=Decimal("100000"),
        status="active",
        holdings=[
            Holding(
                ticker="AAPL",
                quantity=Decimal("1"),
                avg_buy_price=Decimal("100"),
                current_price=Decimal("100"),
            )
        ],
    )
    db.add(portfolio)
    await db.flush()
    portfolio_id = portfolio.id
    db.expunge_all()

    monitored = await list_simulation_portfolios_for_update(db)
    loaded = next(row for row in monitored if row.id == portfolio_id)
    assert "holdings" not in inspect(loaded).unloaded
    assert [holding.ticker for holding in loaded.holdings] == ["AAPL"]

    engine = db.bind.sync_engine
    statements = 0

    def _count(*_args):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        again = await get_portfolio_by_id(db, portfolio_id)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert again is loaded
    assert statements == 0
