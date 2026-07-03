from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.models.user import User
from backend.services import share_service

router = APIRouter(tags=["share"])


@router.post("/api/analysis/{analysis_id}/share", responses={404: {"description": "Analysis not found"}})
async def create_share(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = await share_service.get_user_analysis(db, analysis_id, current_user.id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    share = await share_service.get_or_create_shared_report(
        db,
        analysis_id,
        current_user.id,
        datetime.now(UTC),
    )

    return {"token": share.token, "expires_at": share.expires_at.isoformat()}


@router.get(
    "/api/share/{token}",
    responses={
        404: {"description": "Report or analysis data not found"},
        410: {"description": "Shared report has expired"},
    },
)
async def get_shared_report(token: str, db: AsyncSession = Depends(get_db)):
    share = await share_service.get_shared_report(db, token)
    if not share:
        raise HTTPException(status_code=404, detail="Report not found or expired")
    if share.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="This shared report has expired")

    analysis = await share_service.get_analysis_for_share(db, share.analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis data not found")

    return {
        "ticker": analysis.ticker,
        "trade_date": str(analysis.trade_date) if analysis.trade_date else None,
        "signal": analysis.signal,
        # Analyst reports
        "market_report": analysis.market_report,
        "sentiment_report": analysis.sentiment_report,
        "news_report": analysis.news_report,
        "fundamentals_report": analysis.fundamentals_report,
        "macro_report": analysis.macro_report,
        "options_report": analysis.options_report,
        "quant_report": analysis.quant_report,
        "earnings_report": analysis.earnings_report,
        "insider_report": analysis.insider_report,
        "ownership_report": analysis.ownership_report,
        "ratings_report": analysis.ratings_report,
        "short_interest_report": analysis.short_interest_report,
        "valuation_report": analysis.valuation_report,
        "catalyst_report": analysis.catalyst_report,
        "review_report": analysis.review_report,
        "synthesis_report": analysis.synthesis_report or "",
        "audit_report": analysis.audit_report or "",
        "agent_qa_report": analysis.agent_qa_report,
        # Plans & decisions
        "investment_plan": analysis.investment_plan,
        "trader_plan": analysis.trader_plan,
        "final_decision": analysis.final_decision,
        # Debate history
        "bull_history": analysis.bull_history,
        "bear_history": analysis.bear_history,
        "investment_debate_history": analysis.investment_debate_history,
        "risk_debate_history": analysis.risk_debate_history,
        "judge_decision": analysis.judge_decision or "",
        # Trade details
        "trader_proposal_json": analysis.trader_proposal_json or "{}",
        "chart_annotations": analysis.chart_annotations,
        "risk_metrics": analysis.risk_metrics,
        "quality": analysis.quality,
        "degraded": bool(analysis.degraded) if analysis.degraded is not None else False,
        "failed_agents": analysis.failed_agents or [],
        # Backward-compatible aliases
        "fundamental_report": analysis.fundamentals_report,
        "research_report": analysis.investment_plan,
        # Metadata
        "duration_seconds": analysis.duration_seconds,
        "llm_provider": analysis.llm_provider,
        "llm_model": analysis.llm_model,
        "expires_at": share.expires_at.isoformat(),
        "created_at": share.created_at.isoformat(),
    }
