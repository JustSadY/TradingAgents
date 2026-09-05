from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.models.user import User
from backend.repositories.portfolio import (
    get_or_create_simulation_portfolio,
    get_portfolio_by_id,
    list_holdings,
    list_orders,
    list_portfolios,
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


async def test_portfolio_history_queries_exclude_internal_payloads(
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
    )
    db.add(portfolio)
    await db.flush()
    db.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker="NVDA",
            quantity=Decimal("1"),
            avg_buy_price=Decimal("100"),
            current_price=Decimal("101"),
            entry_commission=Decimal("1"),
            interest_accrued=Decimal("2"),
        )
    )
    db.add(
        Order(
            portfolio_id=portfolio.id,
            broker="paper",
            ticker="NVDA",
            action="BUY",
            quantity_requested=Decimal("1"),
            quantity_filled=Decimal("1"),
            status="FILLED",
            ai_signal="Buy",
            ai_reasoning="large internal reasoning",
            entry_commission=Decimal("1"),
            financing_cost=Decimal("2"),
            external_order_id="internal-id",
        )
    )
    await db.flush()
    db.expunge_all()

    engine = db.bind.sync_engine
    sql_statements: list[str] = []

    def _capture(_conn, _cursor, statement, *_args):
        sql_statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        await list_portfolios(db, user=test_user)
        await list_holdings(db, user=test_user)
        await list_orders(db, user=test_user)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    order_sql = next(sql for sql in sql_statements if " from orders" in sql)
    assert "orders.ai_signal" in order_sql
    assert "orders.ai_reasoning" not in order_sql
    assert "orders.external_order_id" not in order_sql
    assert "orders.entry_commission" not in order_sql
    assert "orders.financing_cost" not in order_sql

    holding_sqls = [sql for sql in sql_statements if " from holdings" in sql]
    assert holding_sqls
    assert all("holdings.ticker" in sql for sql in holding_sqls)
    assert all("holdings.entry_commission" not in sql for sql in holding_sqls)
    assert all("holdings.interest_accrued" not in sql for sql in holding_sqls)
    assert all("holdings.interest_updated_at" not in sql for sql in holding_sqls)
