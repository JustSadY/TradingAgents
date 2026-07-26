from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.portfolio import HoldingRead, OrderRead, PortfolioRead
from backend.services import portfolio_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=list[PortfolioRead])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await portfolio_service.list_user_portfolios(db, current_user)


@router.get("/holdings", response_model=list[HoldingRead])
async def list_holdings(
    mode: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await portfolio_service.list_user_holdings(db, current_user, mode)


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(
    mode: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await portfolio_service.list_user_orders(
        db, current_user, mode=mode, ticker=ticker, limit=limit, offset=offset
    )
