from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.portfolio import Holding, Portfolio
from backend.repositories.portfolio import get_active_holdings_by_portfolio_id, get_simulation_portfolio


async def get_user_simulation_portfolio(db: AsyncSession, user_id: int) -> Portfolio | None:
    return await get_simulation_portfolio(db, user_id)


async def get_active_holdings(db: AsyncSession, portfolio_id: int) -> list[Holding]:
    return await get_active_holdings_by_portfolio_id(db, portfolio_id)
