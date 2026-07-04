from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.models.user import User
from backend.schemas.market import FormulaAssistResponse
from backend.services.market_service import (
    MarketDataError,
    get_custom_indicator_series,
    get_ohlcv,
    get_sentiment_history,
)

router = APIRouter(prefix="/api/market", tags=["market"])

_TICKER_DESCRIPTION = "Ticker symbol, e.g. AAPL"


class FormulaAssistRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500, description="Plain-language indicator description")


@router.get("/ohlcv", response_model=dict[str, Any])
async def ohlcv(
    ticker: str = Query(..., description=_TICKER_DESCRIPTION),
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    period: str = Query("1y", description="1m|3m|6m|1y|2y|5y — ignored when start_date provided"),
    _: User = Depends(get_current_user),
):
    try:
        return await get_ohlcv(ticker, period, start_date, end_date)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/custom-indicator", response_model=dict[str, Any])
async def custom_indicator(
    ticker: str = Query(..., description=_TICKER_DESCRIPTION),
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


@router.post("/formula-assist", response_model=FormulaAssistResponse)
@limiter.limit("10/minute")
async def formula_assist(
    request: Request,
    body: FormulaAssistRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a custom-indicator formula from a plain-language description.

    ValueError from the service (missing key, unsupported request, invalid
    LLM output) maps to 400 via the central exception handler.
    """
    from backend.services.formula_assist_service import generate_formula

    formula = await generate_formula(db, body.prompt, current_user)
    return {"formula": formula}


@router.get("/sentiment-history", response_model=list[dict[str, Any]])
async def sentiment_history(
    ticker: str = Query(..., description=_TICKER_DESCRIPTION),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await get_sentiment_history(db, ticker, user=current_user)
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
