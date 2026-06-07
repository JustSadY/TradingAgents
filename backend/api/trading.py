from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.core.utils import safe_ticker_component
from backend.services import mock_trading_service as svc

router = APIRouter(prefix="/api/trading", tags=["trading"])


class OrderRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    action: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0, le=100_000)
    analysis_id: int | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        try:
            return safe_ticker_component(v, max_len=20)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ResetRequest(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)


@router.get("/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.get_portfolio_with_live_prices(db, user=_)


@router.post("/order", status_code=status.HTTP_201_CREATED)
async def create_order(
    req: OrderRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    # Service raises ValueError for business-rule violations (-> 400 centrally);
    # unexpected errors are logged + 500'd by the global handler.
    result = await svc.execute_order(
        db,
        ticker=req.ticker,
        action=req.action,
        quantity=req.quantity,
        analysis_id=req.analysis_id,
        user=_,
    )
    await db.commit()
    return result


@router.get("/performance")
async def get_performance(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return await svc.get_performance(db, user=_)


@router.post("/reset")
async def reset_portfolio(
    req: ResetRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    result = await svc.reset_portfolio(db, initial_capital=req.initial_capital, user=_)
    await db.commit()
    return result
