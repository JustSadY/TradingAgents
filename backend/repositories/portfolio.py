from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.repositories.common import scope_to_user

async def get_portfolio_by_id(db: AsyncSession, portfolio_id: int, user=None) -> Portfolio | None:
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

async def get_holding(db: AsyncSession, portfolio_id: int, ticker: str) -> Holding | None:
    result = await db.execute(
        select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.ticker == ticker,
        )
    )
    return result.scalar_one_or_none()

async def list_portfolios(db: AsyncSession, user=None) -> list[Portfolio]:
    q = select(Portfolio).options(selectinload(Portfolio.holdings))
    q = scope_to_user(q, Portfolio, user)
    result = await db.execute(q)
    return list(result.scalars().all())

async def list_holdings(db: AsyncSession, user=None, mode: str | None = None) -> list[Holding]:
    q = select(Holding).join(Portfolio)
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
    q = select(Order).order_by(desc(Order.created_at)).limit(limit).offset(offset)
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
