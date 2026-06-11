from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.services.market_service import (
    MarketDataError,
    get_custom_indicator_series,
    get_ohlcv,
    get_sentiment_history,
)

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/ohlcv")
async def ohlcv(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    period: str = Query("1y", description="1m|3m|6m|1y|2y|5y — ignored when start_date provided"),
    _: User = Depends(get_current_user),
):
    try:
        return await get_ohlcv(ticker, period, start_date, end_date)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/custom-indicator")
async def custom_indicator(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    formula: str = Query(..., description="Mathematical formula, e.g. (Close - SMA(20)) / STD(20)"),
    period: str = Query("1y", description="1m|3m|6m|1y|2y|5y"),
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    _: User = Depends(get_current_user),
):
    try:
        return await get_custom_indicator_series(ticker, formula, period, start_date, end_date)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/sentiment-history")
async def sentiment_history(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await get_sentiment_history(db, ticker, user=current_user)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
