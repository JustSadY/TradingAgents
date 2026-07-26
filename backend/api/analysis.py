import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import require_admin, require_any_page, require_page
from backend.core.database import get_db
from backend.core.limiter import limiter
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.schemas.analysis import (
    ABComparisonItem,
    ActiveTaskRead,
    AnalysisListItem,
    AnalysisResultRead,
    AnalysisRunRequest,
    AnalysisRunResponse,
    CancelTaskResponse,
    ChatMessageCreate,
    ChatMessageRead,
    CheckpointItem,
    CostEstimateResponse,
    PerformanceAttributionResponse,
    PerformanceResponse,
    TimeTravelRequest,
    TimeTravelResponse,
)
from backend.schemas.portfolio_analysis import (
    MultiTickerListItem,
    MultiTickerResultRead,
    MultiTickerRunRequest,
    MultiTickerRunResponse,
)
from backend.services.settings_service import get_or_create_settings

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_ANALYSIS_NOT_FOUND = "Analysis not found"


@router.post("/run", response_model=AnalysisRunResponse, responses={422: {"description": "Invalid ticker format"}})
@limiter.limit("5/minute")
async def run_analysis(
    request: Request,
    body: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    try:
        safe_ticker_component(body.ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    settings = await get_or_create_settings(db, current_user)
    task_id = str(uuid.uuid4())
    from backend.services.analysis_queue import dispatch_analysis
    from backend.services.analysis_service import register_task_owner

    await register_task_owner(task_id, current_user.id)
    await dispatch_analysis(
        background_tasks,
        ticker=body.ticker,
        trade_date=body.trade_date,
        asset_type=body.asset_type,
        settings=settings,
        task_id=task_id,
        user=current_user,
    )
    return AnalysisRunResponse(task_id=task_id, ticker=body.ticker, trade_date=body.trade_date)


@router.get("/active", response_model=list[ActiveTaskRead])
async def get_active_tasks(
    current_user: User = Depends(require_page("analysis")),
):
    from backend.services.analysis_service import get_active_tasks_for_user

    return await get_active_tasks_for_user(current_user.id)


@router.get("/latest", response_model=AnalysisResultRead, responses={404: {"description": "No completed analyses"}})
async def get_latest_analysis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    from backend.repositories.analysis import get_latest_analysis as _repo_latest

    row = await _repo_latest(db, user=current_user)
    if row is None:
        raise HTTPException(status_code=404, detail="No completed analyses found")
    from backend.services.token_analytics_service import estimate_cost

    row.estimated_cost_usd = estimate_cost(
        row.llm_provider, row.llm_model, int(row.tokens_in or 0), int(row.tokens_out or 0)
    )
    return row


@router.get("/history", response_model=list[AnalysisListItem])
async def list_analysis(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_page("analysis", "chart", "performance", "dashboard")),
):
    from backend.repositories.analysis import list_analyses as _repo_list

    return await _repo_list(db, user=current_user, ticker=ticker, limit=limit, offset=offset)


@router.post("/{task_id}/cancel", response_model=CancelTaskResponse, responses={404: {"description": "Task not found"}})
async def cancel_analysis(
    task_id: str,
    current_user: User = Depends(require_page("analysis")),
):
    from backend.services.analysis_service import cancel_analysis as _cancel
    from backend.services.analysis_service import is_task_owner

    if not await is_task_owner(task_id, current_user.id, getattr(current_user, "is_admin", False)):
        raise HTTPException(status_code=404, detail="Task not found")
    cancelled = await _cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


@router.get("/cost-estimate", response_model=CostEstimateResponse)
async def cost_estimate(
    user: User = Depends(require_page("analysis")),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.agent_settings_service import get_user_agent_settings
    from backend.services.analysis_stats_service import estimate_cost as _est
    from backend.services.settings_service import get_or_create_settings
    from backend.trading_agents.agent_catalog import list_analysts

    settings = await get_or_create_settings(db, user)
    agent_settings = await get_user_agent_settings(db, user)

    analyst_keys = {a.key for a in list_analysts()}
    enabled_analysts = [k for k, val in agent_settings.agents.items() if val.enabled and k in analyst_keys]
    if not enabled_analysts:
        enabled_analysts = ["market", "news", "fundamentals", "social"]

    analysts_str = ",".join(enabled_analysts)
    debate_rounds = settings.max_debate_rounds or 1
    model = settings.llm_model or "gpt-4o"
    return _est(analysts_str, debate_rounds, model, settings.llm_provider)


@router.get("/ab-comparison", response_model=list[ABComparisonItem])
async def get_ab_comparison(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    from backend.services.analysis_stats_service import get_ab_comparison as _ab

    return await _ab(db, user_id=None)


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("performance")),
):
    from backend.services.analysis_stats_service import get_signal_performance as _perf

    return await _perf(db, ticker, user_id=current_user.id)


@router.get("/performance-attribution", response_model=PerformanceAttributionResponse)
async def get_performance_attribution(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_page("performance", "dashboard")),
):
    from backend.services.performance_service import get_analyst_attribution_stats as _attr

    return await _attr(db, user_id=current_user.id)


@router.post(
    "/run-portfolio", response_model=MultiTickerRunResponse, responses={422: {"description": "Invalid ticker format"}}
)
async def run_portfolio_run(
    body: MultiTickerRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    tickers = [t.upper() for t in body.tickers]
    for ticker in tickers:
        try:
            safe_ticker_component(ticker)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid ticker {ticker}: {e}") from e
    settings = await get_or_create_settings(db, current_user)
    task_id = str(uuid.uuid4())
    from backend.services.analysis_queue import dispatch_portfolio_analysis
    from backend.services.analysis_service import register_task_owner

    await register_task_owner(task_id, current_user.id)
    await dispatch_portfolio_analysis(
        background_tasks,
        tickers=tickers,
        trade_date=body.trade_date,
        asset_type=body.asset_type,
        settings=settings,
        task_id=task_id,
        user=current_user,
    )
    return MultiTickerRunResponse(task_id=task_id, tickers=tickers, trade_date=body.trade_date)


@router.get("/portfolio-history", response_model=list[MultiTickerListItem])
async def list_portfolio_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
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


@router.get(
    "/portfolio/{portfolio_id}",
    response_model=MultiTickerResultRead,
    responses={404: {"description": "Portfolio analysis not found"}},
)
async def get_portfolio_analysis(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
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


@router.get("/{analysis_id}", response_model=AnalysisResultRead, responses={404: {"description": _ANALYSIS_NOT_FOUND}})
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    from backend.repositories.analysis import get_analysis_by_id as _repo_get

    row = await _repo_get(db, analysis_id, user=current_user)
    if row is None:
        raise HTTPException(status_code=404, detail=_ANALYSIS_NOT_FOUND)
    from backend.services.token_analytics_service import estimate_cost

    row.estimated_cost_usd = estimate_cost(
        row.llm_provider, row.llm_model, int(row.tokens_in or 0), int(row.tokens_out or 0)
    )
    return row


@router.get("/{analysis_id}/chat", response_model=list[ChatMessageRead])
async def get_analysis_chat(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    from backend.services.report_chat_service import get_chat_history

    return await get_chat_history(db, analysis_id, current_user)


@router.post("/{analysis_id}/chat", response_model=ChatMessageRead)
async def ask_analysis_report(
    analysis_id: int,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    from backend.services.report_chat_service import answer_report_question

    return await answer_report_question(db, analysis_id, body.message, current_user)


@router.get(
    "/{analysis_id}/checkpoints",
    response_model=list[CheckpointItem],
    responses={404: {"description": _ANALYSIS_NOT_FOUND}},
)
async def list_checkpoints(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    from backend.services.analysis_service import list_analysis_checkpoints

    result = await list_analysis_checkpoints(analysis_id, db, current_user)
    if result is None:
        raise HTTPException(status_code=404, detail=_ANALYSIS_NOT_FOUND)
    return result


@router.post(
    "/{analysis_id}/time-travel",
    response_model=TimeTravelResponse,
    responses={400: {"description": "Invalid checkpoint or state"}, 404: {"description": _ANALYSIS_NOT_FOUND}},
)
async def time_travel_resume(
    analysis_id: int,
    body: TimeTravelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_page("analysis")),
):
    import uuid

    from backend.repositories.analysis import get_analysis_by_id
    from backend.services.analysis_service import rollback_and_resume_analysis

    analysis = await get_analysis_by_id(db, analysis_id, user=current_user)
    if not analysis:
        raise HTTPException(status_code=404, detail=_ANALYSIS_NOT_FOUND)

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
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"task_id": task_id, "ticker": analysis.ticker, "trade_date": analysis.trade_date}
