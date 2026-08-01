from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.order import Order
from backend.models.portfolio import Holding, Portfolio
from backend.models.user import User
from backend.repositories.portfolio import get_active_holdings_by_portfolio_id, get_simulation_portfolio

async def get_user_simulation_portfolio(db: AsyncSession, user_id: int) -> Portfolio | None:
    return await get_simulation_portfolio(db, user_id)

async def get_active_holdings(db: AsyncSession, portfolio_id: int) -> list[Holding]:
    return await get_active_holdings_by_portfolio_id(db, portfolio_id)

async def list_user_portfolios(db: AsyncSession, user: User) -> list[Portfolio]:
    from backend.repositories.portfolio import list_portfolios

    return await list_portfolios(db, user=user)

async def list_user_holdings(db: AsyncSession, user: User, mode: str | None) -> list[Holding]:
    from backend.repositories.portfolio import list_holdings

    return await list_holdings(db, user=user, mode=mode)

async def list_user_orders(
    db: AsyncSession,
    user: User,
    *,
    mode: str | None,
    ticker: str | None,
    limit: int,
    offset: int,
) -> list[Order]:
    from backend.repositories.portfolio import list_orders

    return await list_orders(db, user=user, mode=mode, ticker=ticker, limit=limit, offset=offset)
