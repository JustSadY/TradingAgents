from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, require_page
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
    current_user: User = Depends(require_page("screener")),
):
    """Score a ticker universe and return the strongest candidates."""
    return ScreenResponse(results=await run_screen(universe=body.tickers, top_n=body.top_n))


async def _scan_saved_watchlist(db: AsyncSession, current_user: User) -> dict:
    from backend.services.settings_service import get_or_create_settings

    settings = await get_or_create_settings(db, current_user)
    watchlist = list(getattr(settings, "watchlist", None) or [])
    if not watchlist:
        raise HTTPException(status_code=400, detail="Watchlist is empty")

    # Screening performs slow provider I/O; the watchlist is already detached
    # from the ORM row, so release the request transaction first.
    await db.commit()
    return {"results": await run_screen(universe=watchlist, top_n=len(watchlist))}


@router.post("/scan-watchlist", response_model=ScreenResponse, responses={400: {"description": "Watchlist is empty"}})
@limiter.limit("10/minute")
async def scan_watchlist(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("screener")),
):
    """Score the caller's saved watchlist tickers."""
    return await _scan_saved_watchlist(db, current_user)
