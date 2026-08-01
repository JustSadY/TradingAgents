from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_page
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.portfolio import CorrelationResponse
from backend.services.correlation_service import compute_correlation_matrix
from backend.services.portfolio_service import get_active_holdings, get_user_simulation_portfolio

router = APIRouter(prefix="/api/trading", tags=["trading"])

@router.get("/correlation", response_model=CorrelationResponse)
async def get_correlation(
    period: str = Query(default="90d", pattern=r"^(30d|90d|180d|1y)$", description="Data period: 30d, 90d, 180d, 1y"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("portfolio")),
) -> dict[str, Any]:
    """Compute pairwise correlation matrix for the user's current holdings."""
    portfolio = await get_user_simulation_portfolio(db, current_user.id)

    if portfolio is None:
        return {"tickers": [], "matrix": [], "avg_correlation": None, "warning": "No portfolio found"}

    holdings = await get_active_holdings(db, portfolio.id)
    tickers = [h.ticker for h in holdings]

    return await compute_correlation_matrix(tickers, period)
