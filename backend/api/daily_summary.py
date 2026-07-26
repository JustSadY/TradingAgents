from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_page
from backend.core.database import get_db
from backend.models.user import User
from backend.schemas.daily_summary import DailySummaryResponse
from backend.services.daily_summary_service import generate_daily_summary, get_latest_summary

router = APIRouter(prefix="/api/market", tags=["daily-summary"])


@router.get("/daily-summary", response_model=DailySummaryResponse)
async def fetch_daily_summary(
    current_user: Annotated[User, Depends(require_page("dashboard"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    summary = await get_latest_summary(db, current_user.id)
    return DailySummaryResponse(**summary) if summary else DailySummaryResponse()


@router.post(
    "/daily-summary/generate",
    response_model=DailySummaryResponse,
    responses={
        400: {"description": "Invalid parameter or request value"},
        500: {"description": "Summary generation failed"},
    },
)
async def trigger_daily_summary(
    current_user: Annotated[User, Depends(require_page("dashboard"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        result = await generate_daily_summary(db, current_user)
        return DailySummaryResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {e}") from e
