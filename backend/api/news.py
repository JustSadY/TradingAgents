from fastapi import APIRouter, Depends, Query

from backend.api.deps import require_page
from backend.models.user import User
from backend.schemas.news import NewsItem
from backend.services.news_service import get_news_feed

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/feed", response_model=list[NewsItem])
async def news_feed(
    tickers: str = Query(..., description="Comma-separated ticker list, e.g. AAPL,TSLA"),
    limit: int = Query(default=5, ge=1, le=20),
    _: User = Depends(require_page("dashboard")),
):
    return await get_news_feed(tickers, limit)
