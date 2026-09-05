from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload
from sqlalchemy.orm.util import identity_key

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.repositories.common import scope_to_user

_PORTFOLIO_LIST_COLUMNS = (
    Portfolio.id,
    Portfolio.mode,
    Portfolio.broker,
    Portfolio.initial_capital,
    Portfolio.current_balance,
    Portfolio.cash_available,
    Portfolio.status,
    Portfolio.created_at,
    Portfolio.updated_at,
)
_HOLDING_LIST_COLUMNS = (
    Holding.id,
    Holding.ticker,
    Holding.quantity,
    Holding.avg_buy_price,
    Holding.current_price,
    Holding.unrealized_pnl,
    Holding.side,
    Holding.leverage,
    Holding.margin_used,
    Holding.borrowed_amount,
    Holding.liquidation_price,
    Holding.stop_loss,
    Holding.take_profit,
    Holding.updated_at,
    Holding.opened_at,
)
_ORDER_LIST_COLUMNS = (
    Order.id,
    Order.portfolio_id,
    Order.broker,
    Order.ticker,
    Order.action,
    Order.quantity_requested,
    Order.quantity_filled,
    Order.status,
    Order.price_per_share,
    Order.total_value,
    Order.commission,
    Order.leverage,
    Order.side,
    Order.realized_pnl,
    Order.analysis_id,
    Order.ai_signal,
    Order.created_at,
    Order.executed_at,
)


def _cached_portfolio_with_holdings(db: AsyncSession, portfolio_id: int, user=None) -> Portfolio | None:
    """Reuse an already-loaded portfolio only when its holdings collection is ready."""
    cached = db.identity_map.get(identity_key(Portfolio, portfolio_id))
    if cached is None or "holdings" in inspect(cached).unloaded:
        return None
    if user is not None and not getattr(user, "is_admin", False) and cached.user_id != user.id:
        return None
    return cached


async def get_portfolio_by_id(db: AsyncSession, portfolio_id: int, user=None) -> Portfolio | None:
    cached = _cached_portfolio_with_holdings(db, portfolio_id, user=user)
    if cached is not None:
        return cached
    q = select(Portfolio).where(Portfolio.id == portfolio_id).options(selectinload(Portfolio.holdings))
    q = scope_to_user(q, Portfolio, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()

async def get_simulation_portfolio(db: AsyncSession, user_id: int | None = None) -> Portfolio | None:
    q = select(Portfolio).where(Portfolio.mode == "simulation").options(selectinload(Portfolio.holdings))
    if user_id is not None:
        q = q.where(Portfolio.user_id == user_id)
    else:
        q = q.where(Portfolio.user_id.is_(None))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_or_create_simulation_portfolio(
    db: AsyncSession,
    *,
    user_id: int | None,
    initial_capital: Decimal,
) -> Portfolio:
    """Return the tenant's simulation portfolio, creating it race-safely."""
    portfolio = await get_simulation_portfolio(db, user_id=user_id)
    if portfolio is None:
        try:
            async with db.begin_nested():
                portfolio = Portfolio(
                    mode="simulation",
                    broker="paper",
                    initial_capital=initial_capital,
                    current_balance=initial_capital,
                    cash_available=initial_capital,
                    status="active",
                    user_id=user_id,
                    holdings=[],
                )
                db.add(portfolio)
                await db.flush()
        except IntegrityError:
            portfolio = await get_simulation_portfolio(db, user_id=user_id)
            if portfolio is None:
                raise
    # Existing rows already arrive with holdings select-in loaded, and a newly
    # created portfolio starts with an explicitly initialized empty collection.
    # Avoid an extra relationship refresh on this hot get-or-create path.
    return portfolio


async def lock_portfolio_for_update(db: AsyncSession, portfolio_id: int) -> Portfolio:
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update(),
        execution_options={"populate_existing": True},
    )
    return result.scalar_one()


async def list_simulation_portfolios_for_update(db: AsyncSession) -> list[Portfolio]:
    # The position monitor immediately reads every holding. Load all holdings in
    # one secondary query so the subsequent per-portfolio snapshot can reuse the
    # identity-mapped objects instead of issuing two queries per portfolio.
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.mode == "simulation")
        .options(selectinload(Portfolio.holdings))
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def reset_simulation_portfolio(
    db: AsyncSession,
    *,
    user_id: int | None,
    initial_capital: Decimal,
) -> Portfolio:
    portfolio = await get_or_create_simulation_portfolio(
        db,
        user_id=user_id,
        initial_capital=initial_capital,
    )
    portfolio = await lock_portfolio_for_update(db, portfolio.id)
    await db.execute(delete(Order).where(Order.portfolio_id == portfolio.id))
    await db.execute(delete(Holding).where(Holding.portfolio_id == portfolio.id))
    portfolio.cash_available = initial_capital
    portfolio.current_balance = initial_capital
    portfolio.initial_capital = initial_capital
    portfolio.margin_used = Decimal("0.0")
    await db.flush()
    return portfolio


def stage_order(db: AsyncSession, **values: Any) -> Order:
    """Stage an already-authorized order row for the caller's transaction."""
    order = Order(**values)
    db.add(order)
    return order


def stage_holding(db: AsyncSession, **values: Any) -> Holding:
    """Stage an already-computed holding row for the caller's transaction."""
    holding = Holding(**values)
    db.add(holding)
    return holding


async def delete_holding_row(db: AsyncSession, holding: Holding) -> None:
    await db.delete(holding)


async def flush_portfolio_changes(db: AsyncSession) -> None:
    await db.flush()


async def get_holding(db: AsyncSession, portfolio_id: int, ticker: str) -> Holding | None:
    result = await db.execute(
        select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.ticker == ticker,
        )
    )
    return result.scalar_one_or_none()

async def list_portfolios(db: AsyncSession, user=None) -> list[Portfolio]:
    q = select(Portfolio).options(
        load_only(*_PORTFOLIO_LIST_COLUMNS),
        selectinload(Portfolio.holdings).load_only(*_HOLDING_LIST_COLUMNS),
    )
    q = scope_to_user(q, Portfolio, user)
    result = await db.execute(q)
    return list(result.scalars().all())

async def list_holdings(db: AsyncSession, user=None, mode: str | None = None) -> list[Holding]:
    q = select(Holding).options(load_only(*_HOLDING_LIST_COLUMNS)).join(Portfolio)
    q = scope_to_user(q, Portfolio, user)
    if mode:
        q = q.where(Portfolio.mode == mode)
    result = await db.execute(q)
    return list(result.scalars().all())

async def get_order_by_id(db: AsyncSession, order_id: int, user=None) -> Order | None:
    """Fetch an order by id, scoped to the requesting user's portfolios.

    Orders carry no ``user_id`` of their own — ownership is via
    ``Portfolio.user_id`` — so callers must go through here (not a bare
    ``Order.id`` lookup) to avoid cross-user access (IDOR).
    """
    q = select(Order).where(Order.id == order_id)
    if user and not getattr(user, "is_admin", False):
        q = q.join(Portfolio)
    q = scope_to_user(q, Portfolio, user)
    result = await db.execute(q)
    return result.scalar_one_or_none()

async def list_orders(
    db: AsyncSession,
    user=None,
    mode: str | None = None,
    ticker: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    q = (
        select(Order)
        .options(load_only(*_ORDER_LIST_COLUMNS))
        .order_by(desc(Order.created_at))
        .limit(limit)
        .offset(offset)
    )
    need_portfolio_join = (user and not getattr(user, "is_admin", False)) or mode
    if need_portfolio_join:
        q = q.join(Portfolio)
    q = scope_to_user(q, Portfolio, user)
    if mode:
        q = q.where(Portfolio.mode == mode)
    if ticker:
        q = q.where(Order.ticker == ticker.upper())
    result = await db.execute(q)
    return list(result.scalars().all())

async def get_active_holdings_by_portfolio_id(db: AsyncSession, portfolio_id: int) -> list[Holding]:
    result = await db.execute(
        select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.quantity > 0,
        )
    )
    return list(result.scalars().all())
