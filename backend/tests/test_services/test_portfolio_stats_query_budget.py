from __future__ import annotations

from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Portfolio
from backend.models.user import User
from backend.services.portfolio_stats_service import get_portfolio_stats


async def test_portfolio_stats_loads_only_analytics_columns(
    db: AsyncSession,
    test_user: User,
) -> None:
    portfolio = Portfolio(
        user_id=test_user.id,
        mode="simulation",
        broker="paper",
        initial_capital=Decimal("100000"),
        current_balance=Decimal("100500"),
        cash_available=Decimal("100500"),
        status="active",
    )
    db.add(portfolio)
    await db.flush()
    db.add(
        Order(
            portfolio_id=portfolio.id,
            broker="paper",
            ticker="AAPL",
            action="SELL",
            side="long",
            quantity_requested=Decimal("1"),
            quantity_filled=Decimal("1"),
            status="FILLED",
            price_per_share=Decimal("110"),
            total_value=Decimal("110"),
            commission=Decimal("0.1"),
            entry_commission=Decimal("0.1"),
            realized_pnl=Decimal("9.8"),
            financing_cost=Decimal("3"),
            external_order_id="internal-provider-id",
            ai_signal="Buy",
            ai_reasoning="large internal explanation that stats never use",
        )
    )
    await db.flush()
    db.expunge_all()

    statements: list[str] = []
    engine = db.bind.sync_engine

    def _capture(_conn, _cursor, statement, *_args):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        result = await get_portfolio_stats(db, test_user)
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert result["total_trades"] == 1

    portfolio_sql = next(sql for sql in statements if " from portfolios" in sql)
    portfolio_select = portfolio_sql.split(" from ", 1)[0]
    assert "portfolios.id" in portfolio_select
    assert "portfolios.initial_capital" in portfolio_select
    assert "portfolios.current_balance" not in portfolio_select
    assert "portfolios.cash_available" not in portfolio_select
    assert "portfolios.margin_used" not in portfolio_select

    order_sql = next(sql for sql in statements if " from orders" in sql)
    order_select = order_sql.split(" from ", 1)[0]
    assert "orders.entry_commission" in order_select
    assert "orders.realized_pnl" in order_select
    assert "orders.ai_reasoning" not in order_select
    assert "orders.external_order_id" not in order_select
    assert "orders.financing_cost" not in order_select
