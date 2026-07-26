from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_page
from backend.core.database import get_db
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.services.market_data_service import get_live_prices_details_batch
from backend.services.settings_service import (
    add_ticker_to_watchlist,
    get_or_create_settings,
    remove_ticker_from_watchlist,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[str])
async def get_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("watchlist")),
):
    settings = await get_or_create_settings(db, current_user)
    return settings.watchlist


@router.get("/prices", response_model=dict[str, dict[str, float]])
async def get_watchlist_prices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("watchlist")),
):
    settings = await get_or_create_settings(db, current_user)
    if not settings.watchlist:
        return {}
    return await get_live_prices_details_batch(settings.watchlist)


@router.post("/{ticker}", response_model=list[str], responses={422: {"description": "Invalid ticker format"}})
async def add_to_watchlist(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("watchlist")),
):
    try:
        safe_ticker_component(ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return await add_ticker_to_watchlist(db, current_user, ticker.upper())


@router.delete("/{ticker}", response_model=list[str])
async def remove_from_watchlist(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("watchlist")),
):
    return await remove_ticker_from_watchlist(db, current_user, ticker.upper())
