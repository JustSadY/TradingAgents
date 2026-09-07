from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import AnalysisResult
from backend.models.order import Order
from backend.models.user import User
from backend.repositories.trading_execution import (
    apply_broker_account_balances,
    get_or_create_broker_audit_portfolio,
    persist_broker_order,
)


async def test_broker_audit_portfolio_is_reused_and_resynchronized(
    db: AsyncSession,
    test_user: User,
) -> None:
    first = await get_or_create_broker_audit_portfolio(
        db,
        user_id=test_user.id,
        mode="live",
        equity=Decimal("10000"),
        cash=Decimal("4000"),
    )
    await db.flush()
    second = await get_or_create_broker_audit_portfolio(
        db,
        user_id=test_user.id,
        mode="live",
        equity=Decimal("11000"),
        cash=Decimal("4500"),
    )

    assert second.id == first.id
    assert second.mode == "live"
    assert second.broker == "alpaca"
    assert second.current_balance == Decimal("11000")
    assert second.cash_available == Decimal("4500")


async def test_broker_order_audit_persists_canonical_result_fields(
    db: AsyncSession,
    test_user: User,
) -> None:
    portfolio = await get_or_create_broker_audit_portfolio(
        db,
        user_id=test_user.id,
        mode="simulation",
        equity=Decimal("10000"),
        cash=Decimal("5000"),
    )
    executed_at = datetime.now(UTC)
    order = await persist_broker_order(
        db,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        action="BUY",
        side="long",
        leverage=Decimal("1"),
        quantity_requested=Decimal("2"),
        quantity_filled=Decimal("2"),
        status="FILLED",
        price_per_share=Decimal("200"),
        total_value=Decimal("400"),
        commission=Decimal("0"),
        external_order_id="alpaca-1",
        analysis_id=None,
        ai_signal="Buy",
        ai_reasoning="reason",
        executed_at=executed_at,
    )

    assert order.portfolio_id == portfolio.id
    assert order.broker == "alpaca"
    assert order.external_order_id == "alpaca-1"
    assert order.quantity_filled == Decimal("2")
    assert order.total_value == Decimal("400")


async def test_analysis_broker_audit_retry_reuses_the_same_order_row(
    db: AsyncSession,
    test_user: User,
) -> None:
    portfolio = await get_or_create_broker_audit_portfolio(
        db,
        user_id=test_user.id,
        mode="simulation",
        equity=Decimal("10000"),
        cash=Decimal("5000"),
    )
    analysis = AnalysisResult(
        user_id=test_user.id,
        ticker="AAPL",
        trade_date="2026-09-07",
        signal="Buy",
    )
    db.add(analysis)
    await db.flush()

    first = await persist_broker_order(
        db,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        action="BUY",
        side="long",
        leverage=Decimal("1"),
        quantity_requested=Decimal("2"),
        quantity_filled=Decimal("0"),
        status="RECONCILIATION_REQUIRED",
        price_per_share=None,
        total_value=None,
        commission=Decimal("0"),
        external_order_id="client:ta-analysis-1",
        analysis_id=analysis.id,
        ai_signal="Buy",
        ai_reasoning="first snapshot",
        executed_at=None,
    )
    first_id = first.id

    second = await persist_broker_order(
        db,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        action="BUY",
        side="long",
        leverage=Decimal("1"),
        quantity_requested=Decimal("2"),
        quantity_filled=Decimal("2"),
        status="FILLED",
        price_per_share=Decimal("201"),
        total_value=Decimal("402"),
        commission=Decimal("0"),
        external_order_id="alpaca-real-1",
        analysis_id=analysis.id,
        ai_signal="Buy",
        ai_reasoning="recovered snapshot",
        executed_at=datetime.now(UTC),
    )

    rows = (
        await db.execute(
            select(Order).where(
                Order.portfolio_id == portfolio.id,
                Order.broker == "alpaca",
                Order.analysis_id == analysis.id,
            )
        )
    ).scalars().all()

    assert second.id == first_id
    assert len(rows) == 1
    assert rows[0].status == "FILLED"
    assert rows[0].external_order_id == "alpaca-real-1"
    assert rows[0].quantity_filled == Decimal("2")
    assert rows[0].price_per_share == Decimal("201")


def test_apply_broker_account_balances_only_updates_authoritative_balances() -> None:
    class PortfolioStub:
        cash_available = Decimal("1")
        current_balance = Decimal("2")
        initial_capital = Decimal("3")

    portfolio = PortfolioStub()
    apply_broker_account_balances(
        portfolio,
        cash=Decimal("10"),
        equity=Decimal("20"),
    )

    assert portfolio.cash_available == Decimal("10")
    assert portfolio.current_balance == Decimal("20")
    assert portfolio.initial_capital == Decimal("3")
