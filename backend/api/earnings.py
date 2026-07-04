from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.core.limiter import limiter
from backend.models.user import User
from backend.schemas.common import EarningsCalendarResponse
from backend.services.earnings_service import get_earnings_calendar

router = APIRouter(prefix="/api/market", tags=["earnings"])


@router.get("/earnings-calendar", response_model=EarningsCalendarResponse)
@limiter.limit("20/minute")
async def earnings_calendar(
    request: Request,
    tickers: str | None = Query(
        default=None,
        description="Comma-separated tickers. Defaults to user's watchlist.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return upcoming earnings data for the given tickers (or user watchlist)."""
    results = await get_earnings_calendar(db, current_user, tickers)
    return {"results": results}
