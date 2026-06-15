from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.models.user import User
from backend.services.daily_summary_service import generate_daily_summary, get_latest_summary

router = APIRouter(prefix="/api/market", tags=["daily-summary"])


@router.get("/daily-summary")
async def fetch_daily_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_latest_summary(db, current_user.id)
    return summary or {}


@router.post("/daily-summary/generate")
async def trigger_daily_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await generate_daily_summary(db, current_user)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {e}") from e
