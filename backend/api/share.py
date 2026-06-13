from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.models.analysis import AnalysisResult
from backend.models.shared_report import SharedReport
from backend.models.user import User

router = APIRouter(tags=["share"])


@router.post("/api/analysis/{analysis_id}/share")
async def create_share(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify user owns the analysis
    result = await db.execute(
        select(AnalysisResult).where(
            AnalysisResult.id == analysis_id,
            AnalysisResult.user_id == current_user.id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Check if a non-expired share already exists for this analysis by this user
    existing = await db.execute(
        select(SharedReport).where(
            SharedReport.analysis_id == analysis_id,
            SharedReport.user_id == current_user.id,
            SharedReport.expires_at > datetime.now(UTC),
        )
    )
    share = existing.scalar_one_or_none()
    if not share:
        share = SharedReport(user_id=current_user.id, analysis_id=analysis_id)
        db.add(share)
        await db.commit()
        await db.refresh(share)

    return {"token": share.token, "expires_at": share.expires_at.isoformat()}


@router.get("/api/share/{token}")
async def get_shared_report(token: str, db: AsyncSession = Depends(get_db)):
    # Public endpoint — no auth
    result = await db.execute(select(SharedReport).where(SharedReport.token == token))
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Report not found or expired")
    if share.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="This shared report has expired")

    # Fetch the analysis
    ar = await db.execute(select(AnalysisResult).where(AnalysisResult.id == share.analysis_id))
    analysis = ar.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis data not found")

    # Return safe subset (no user-identifying info)
    return {
        "ticker": analysis.ticker,
        "trade_date": str(analysis.trade_date) if analysis.trade_date else None,
        "signal": analysis.signal,
        "market_report": analysis.market_report,
        "sentiment_report": analysis.sentiment_report,
        "news_report": analysis.news_report,
        "fundamental_report": analysis.fundamentals_report,
        "research_report": analysis.investment_plan,
        "final_decision": analysis.final_decision,
        "duration_seconds": analysis.duration_seconds,
        "llm_provider": analysis.llm_provider,
        "llm_model": analysis.llm_model,
        "expires_at": share.expires_at.isoformat(),
        "created_at": share.created_at.isoformat(),
    }
