import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import defer
from backend.core.database import get_db
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.analysis import (
    AnalysisRunRequest, AnalysisRunResponse,
    AnalysisResultRead, AnalysisListItem,
    ChatMessageRead, ChatMessageCreate,
)
from backend.schemas.portfolio_analysis import (
    MultiTickerRunRequest, MultiTickerRunResponse,
    MultiTickerListItem, MultiTickerResultRead,
)
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.api.deps import get_current_user
from backend.repositories.common import scope_to_user
from backend.services.settings_service import get_or_create_settings
import json as _json
from backend.core.utils import safe_ticker_component
router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_logger = logging.getLogger(__name__)
@router.post("/run", response_model=AnalysisRunResponse)
async def run_analysis(
    body: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        safe_ticker_component(body.ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    settings = await get_or_create_settings(db, current_user)
    task_id = str(uuid.uuid4())
    from backend.services.analysis_service import run_analysis_task
    background_tasks.add_task(
        run_analysis_task,
        body.ticker, body.trade_date, body.asset_type, settings, task_id, current_user,
    )
    return AnalysisRunResponse(task_id=task_id, ticker=body.ticker, trade_date=body.trade_date)
@router.get("/history", response_model=list[AnalysisListItem])
async def list_analysis(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(AnalysisResult)
        .options(
            defer(AnalysisResult.bull_history),
            defer(AnalysisResult.bear_history),
            defer(AnalysisResult.investment_debate_history),
            defer(AnalysisResult.risk_debate_history),
        )
        .order_by(desc(AnalysisResult.created_at))
        .limit(limit)
        .offset(offset)
    )
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    q = scope_to_user(q, AnalysisResult, current_user)
    result = await db.execute(q)
    return result.scalars().all()
@router.post("/{task_id}/cancel")
async def cancel_analysis(
    task_id: str,
    _: User = Depends(get_current_user),
):
    from backend.services.analysis_service import cancel_analysis as _cancel
    cancelled = await _cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}
@router.get("/cost-estimate")
async def cost_estimate(
    analysts: str = Query(default="market,news,fundamentals,social"),
    debate_rounds: int = Query(default=1, ge=1, le=10),
    model: str = Query(default="gpt-4o"),
    _: User = Depends(get_current_user),
):
    from backend.services.analysis_stats_service import estimate_cost
    return estimate_cost(analysts, debate_rounds, model)
@router.get("/ab-comparison")
async def get_ab_comparison(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from backend.services.analysis_stats_service import get_ab_comparison as _ab
    return await _ab(db)
@router.get("/performance")
async def get_performance(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from backend.services.analysis_stats_service import get_signal_performance
    return await get_signal_performance(db, ticker)
@router.get("/performance-attribution")
async def get_performance_attribution(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from backend.services.performance_service import get_analyst_attribution_stats
    return await get_analyst_attribution_stats(db)
@router.post("/run-portfolio", response_model=MultiTickerRunResponse)
async def run_portfolio(
    body: MultiTickerRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tickers = [t.upper() for t in body.tickers]
    for ticker in tickers:
        try:
            safe_ticker_component(ticker)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid ticker {ticker}: {e}")
    settings = await get_or_create_settings(db, current_user)
    task_id = str(uuid.uuid4())
    from backend.services.analysis_service import run_portfolio_task
    background_tasks.add_task(
        run_portfolio_task,
        tickers, body.trade_date, body.asset_type, settings, current_user,
    )
    return MultiTickerRunResponse(task_id=task_id, tickers=tickers, trade_date=body.trade_date)
@router.get("/portfolio-history", response_model=list[MultiTickerListItem])
async def list_portfolio_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(MultiTickerAnalysis).order_by(desc(MultiTickerAnalysis.created_at)).limit(limit).offset(offset)
    q = scope_to_user(q, MultiTickerAnalysis, current_user)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        MultiTickerListItem(
            id=r.id,
            tickers=r.tickers,
            trade_date=r.trade_date,
            asset_type=r.asset_type,
            triggered_by=r.triggered_by,
            created_at=r.created_at,
        )
        for r in rows
    ]
@router.get("/portfolio/{portfolio_id}", response_model=MultiTickerResultRead)
async def get_portfolio_analysis(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = scope_to_user(
        select(MultiTickerAnalysis).where(MultiTickerAnalysis.id == portfolio_id),
        MultiTickerAnalysis, current_user,
    )
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio analysis not found")
    return MultiTickerResultRead(
        id=row.id,
        tickers=row.tickers,
        trade_date=row.trade_date,
        asset_type=row.asset_type,
        analysis_ids=row.analysis_ids,
        super_portfolio_report=row.super_portfolio_report,
        triggered_by=row.triggered_by,
        created_at=row.created_at,
    )
@router.get("/{analysis_id}", response_model=AnalysisResultRead)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = scope_to_user(
        select(AnalysisResult).where(AnalysisResult.id == analysis_id),
        AnalysisResult, current_user,
    )
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return row
@router.get("/{analysis_id}/chat", response_model=list[ChatMessageRead])
async def get_analysis_chat(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.report_chat_service import get_chat_history
    return await get_chat_history(db, analysis_id, current_user)
@router.post("/{analysis_id}/chat", response_model=ChatMessageRead)
async def ask_analysis_report(
    analysis_id: int,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.report_chat_service import answer_report_question
    return await answer_report_question(db, analysis_id, body.message, current_user)
