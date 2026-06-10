import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.schemas.analysis import (
    AnalysisListItem,
    AnalysisResultRead,
    AnalysisRunRequest,
    AnalysisRunResponse,
    ChatMessageCreate,
    ChatMessageRead,
)
from backend.schemas.portfolio_analysis import (
    MultiTickerListItem,
    MultiTickerResultRead,
    MultiTickerRunRequest,
    MultiTickerRunResponse,
)
from backend.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_logger = logging.getLogger(__name__)


@router.post("/run", response_model=AnalysisRunResponse)
@limiter.limit("5/minute")
async def run_analysis(
    request: Request,
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
    from backend.services.analysis_service import register_task_owner, run_analysis_task

    register_task_owner(task_id, current_user.id)
    background_tasks.add_task(
        run_analysis_task,
        body.ticker,
        body.trade_date,
        body.asset_type,
        settings,
        task_id,
        current_user,
    )
    return AnalysisRunResponse(task_id=task_id, ticker=body.ticker, trade_date=body.trade_date)


@router.get("/active")
async def get_active_tasks(
    current_user: User = Depends(get_current_user),
):
    from backend.services.analysis_service import get_active_tasks_for_user

    return get_active_tasks_for_user(current_user.id)


@router.get("/history", response_model=list[AnalysisListItem])
async def list_analysis(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.analysis import list_analyses as _repo_list

    return await _repo_list(db, user=current_user, ticker=ticker, limit=limit, offset=offset)


@router.post("/{task_id}/cancel")
async def cancel_analysis(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    from backend.services.analysis_service import cancel_analysis as _cancel
    from backend.services.analysis_service import is_task_owner

    if not is_task_owner(task_id, current_user.id, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=404, detail="Task not found")
    cancelled = await _cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


@router.get("/cost-estimate")
async def cost_estimate(
    analysts: str = Query(default="market,news,fundamentals,social"),
    debate_rounds: int = Query(default=1, ge=1, le=10),
    model: str = Query(default="gpt-4o"),
    _: User = Depends(get_current_user),
):
    from backend.services.analysis_stats_service import estimate_cost as _est

    return _est(analysts, debate_rounds, model)


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
    from backend.services.analysis_stats_service import get_signal_performance as _perf

    return await _perf(db, ticker)


@router.get("/performance-attribution")
async def get_performance_attribution(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from backend.services.performance_service import get_analyst_attribution_stats as _attr

    return await _attr(db)


@router.post("/run-portfolio", response_model=MultiTickerRunResponse)
async def run_portfolio_run(
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
    from backend.services.analysis_service import register_task_owner, run_portfolio_task

    register_task_owner(task_id, current_user.id)
    background_tasks.add_task(
        run_portfolio_task,
        tickers,
        body.trade_date,
        body.asset_type,
        settings,
        current_user,
        task_id,
    )
    return MultiTickerRunResponse(task_id=task_id, tickers=tickers, trade_date=body.trade_date)


@router.get("/portfolio-history", response_model=list[MultiTickerListItem])
async def list_portfolio_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.analysis import list_multi_ticker_analyses as _repo_list

    rows = await _repo_list(db, user=current_user, limit=limit, offset=offset)
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
    from backend.repositories.analysis import get_multi_ticker_analysis_by_id as _repo_get

    row = await _repo_get(db, portfolio_id, user=current_user)
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
    from backend.repositories.analysis import get_analysis_by_id as _repo_get

    row = await _repo_get(db, analysis_id, user=current_user)
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


from pydantic import BaseModel

class TimeTravelRequest(BaseModel):
    checkpoint_id: str
    update_state: dict


@router.get("/{analysis_id}/checkpoints")
async def list_checkpoints(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.analysis import get_analysis_by_id
    from backend.trading_agents.graph.checkpointer import list_checkpoints_for_thread
    from backend.services.settings_service import get_or_create_settings
    from backend.repositories.analysis import get_system_settings
    from backend.services.analysis.config_builder import build_analysis_config

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    settings = await get_or_create_settings(db, current_user)
    sys_settings = await get_system_settings(db)
    config = build_analysis_config(settings, user=current_user, sys_settings=sys_settings)

    checkpoints = await list_checkpoints_for_thread(config["data_cache_dir"], analysis.ticker, analysis.trade_date)
    return checkpoints


@router.post("/{analysis_id}/time-travel")
async def time_travel_resume(
    analysis_id: int,
    body: TimeTravelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.repositories.analysis import get_analysis_by_id
    from backend.services.analysis_service import rollback_and_resume_analysis
    import uuid

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    task_id = str(uuid.uuid4())
    try:
        await rollback_and_resume_analysis(
            analysis_id=analysis_id,
            checkpoint_id=body.checkpoint_id,
            update_state=body.update_state,
            current_user=current_user,
            task_id=task_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"task_id": task_id, "ticker": analysis.ticker, "trade_date": analysis.trade_date}
