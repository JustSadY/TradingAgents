import re

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_current_user
from backend.models.user import User
from backend.services.pattern_detection_service import detect_patterns

router = APIRouter(prefix="/api/market", tags=["patterns"])

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_VALID_PERIODS = {"3m", "6m", "1y", "2y"}


@router.get("/patterns/{ticker}")
async def get_patterns(
    ticker: str,
    period: str = Query("1y"),
    current_user: User = Depends(get_current_user),
):
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker")
    if period not in _VALID_PERIODS:
        period = "1y"
    patterns = await detect_patterns(ticker, period)
    return {"ticker": ticker, "period": period, "patterns": patterns}
