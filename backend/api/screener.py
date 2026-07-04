from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.core.limiter import limiter
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.schemas.screener import ScreenResponse
from backend.services.screener_service import MAX_UNIVERSE, run_screen

router = APIRouter(prefix="/api/screener", tags=["screener"])


class ScreenRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, max_length=MAX_UNIVERSE)
    top_n: int = Field(default=10, ge=1, le=MAX_UNIVERSE)

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned = []
        for t in v:
            cleaned.append(safe_ticker_component(t.strip().upper(), max_len=20))
        return cleaned


@router.post("/scan", response_model=ScreenResponse)
@limiter.limit("10/minute")
async def scan(
    request: Request,
    body: ScreenRequest,
    current_user: User = Depends(get_current_user),
):
    """Score a ticker universe and return the strongest candidates."""
    return ScreenResponse(results=await run_screen(universe=body.tickers, top_n=body.top_n))


@router.post("/scan-watchlist", response_model=ScreenResponse, responses={400: {"description": "Watchlist is empty"}})
@limiter.limit("10/minute")
async def scan_watchlist(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Score the caller's saved watchlist tickers."""
    from backend.services.settings_service import get_or_create_settings

    settings = await get_or_create_settings(db, current_user)
    watchlist = list(getattr(settings, "watchlist", None) or [])
    if not watchlist:
        raise HTTPException(status_code=400, detail="Watchlist is empty")
    return {"results": await run_screen(universe=watchlist, top_n=len(watchlist))}
