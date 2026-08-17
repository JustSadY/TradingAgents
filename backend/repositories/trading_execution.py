from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Portfolio


async def _get_broker_audit_portfolio_for_update(
    db: AsyncSession,
    *,
    user_id: int,
    audit_mode: str,
) -> Portfolio | None:
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == user_id, Portfolio.mode == audit_mode)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def get_or_create_broker_audit_portfolio(
    db: AsyncSession,
    *,
    user_id: int,
    mode: str,
    equity: Decimal,
    cash: Decimal,
) -> Portfolio:
    """Lock and synchronize the local Alpaca audit portfolio.

    Broker account state remains authoritative. This row only provides a stable
    local container for order reconciliation and audit history. Creation uses a
    savepoint so concurrent first submissions cannot poison the caller's outer
    transaction when ``uq_portfolio_user_mode`` wins in another session.
    """
    audit_mode = "live" if mode == "live" else "alpaca_paper"
    portfolio = await _get_broker_audit_portfolio_for_update(
        db,
        user_id=user_id,
        audit_mode=audit_mode,
    )
    if portfolio is None:
        try:
            async with db.begin_nested():
                portfolio = Portfolio(
                    user_id=user_id,
                    mode=audit_mode,
                    broker="alpaca",
                    initial_capital=equity if equity > 0 else cash,
                    current_balance=equity,
                    cash_available=cash,
                    margin_used=Decimal("0"),
                    status="active",
                )
                db.add(portfolio)
                await db.flush()
        except IntegrityError:
            portfolio = await _get_broker_audit_portfolio_for_update(
                db,
                user_id=user_id,
                audit_mode=audit_mode,
            )
            if portfolio is None:
                raise
    portfolio.current_balance = equity
    portfolio.cash_available = cash
    portfolio.status = "active"
    return portfolio


async def persist_broker_order(
    db: AsyncSession,
    *,
    portfolio_id: int,
    ticker: str,
    action: str,
    side: str,
    leverage: Decimal,
    quantity_requested: Decimal,
    quantity_filled: Decimal,
    status: str,
    price_per_share: Decimal | None,
    total_value: Decimal | None,
    commission: Decimal,
    external_order_id: str | None,
    analysis_id: int | None,
    ai_signal: str,
    ai_reasoning: str,
    executed_at,
) -> Order:
    """Persist one broker submission/result as an immutable local audit row."""
    order = Order(
        portfolio_id=portfolio_id,
        broker="alpaca",
        ticker=ticker,
        action=action,
        side=side,
        leverage=leverage,
        quantity_requested=quantity_requested,
        quantity_filled=quantity_filled,
        status=status,
        price_per_share=price_per_share,
        total_value=total_value,
        commission=commission,
        entry_commission=Decimal("0"),
        realized_pnl=Decimal("0"),
        financing_cost=Decimal("0"),
        external_order_id=external_order_id,
        analysis_id=analysis_id,
        ai_signal=ai_signal[:50],
        ai_reasoning=ai_reasoning[:4_000],
        executed_at=executed_at,
    )
    db.add(order)
    await db.flush()
    return order


def apply_broker_account_balances(
    portfolio: Portfolio,
    *,
    cash: Decimal,
    equity: Decimal,
) -> None:
    """Apply an already-fetched authoritative broker balance snapshot."""
    portfolio.cash_available = cash
    portfolio.current_balance = equity
