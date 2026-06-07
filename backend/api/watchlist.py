from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[str])
async def get_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = await get_or_create_settings(db, current_user)
    return settings.watchlist


@router.post("/{ticker}", response_model=list[str])
async def add_to_watchlist(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        safe_ticker_component(ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ticker = ticker.upper()
    settings = await get_or_create_settings(db, current_user)
    wl = settings.watchlist
    if ticker not in wl:
        wl.append(ticker)
        settings.watchlist = wl
    await db.flush()
    return settings.watchlist


@router.delete("/{ticker}", response_model=list[str])
async def remove_from_watchlist(
    ticker: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticker = ticker.upper()
    settings = await get_or_create_settings(db, current_user)
    wl = [t for t in settings.watchlist if t != ticker]
    settings.watchlist = wl
    await db.flush()
    return settings.watchlist
