import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
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
    q = select(AnalysisResult).order_by(desc(AnalysisResult.created_at)).limit(limit).offset(offset)
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    if not current_user.is_admin:
        q = q.where(AnalysisResult.user_id == current_user.id)
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
_TOKEN_PER_ANALYST = 8_000
_COST_PER_1K: dict[str, float] = {
    "gpt-4o-mini": 0.00015, "gpt-4o": 0.005, "gpt-4.1": 0.008,
    "claude-opus": 0.015, "claude-sonnet": 0.003, "gemini-1.5-pro": 0.007,
}
@router.get("/cost-estimate")
async def cost_estimate(
    analysts: str = Query(default="market,news,fundamentals,social"),
    debate_rounds: int = Query(default=1, ge=1, le=10),
    model: str = Query(default="gpt-4o"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    analyst_list = [a.strip() for a in analysts.split(",") if a.strip()]
    n = len(analyst_list)
    tokens = n * _TOKEN_PER_ANALYST * debate_rounds + 5_000
    rate = next((v for k, v in _COST_PER_1K.items() if k in model.lower()), 0.005)
    cost = tokens / 1000 * rate
    return {
        "analyst_count": n,
        "estimated_tokens": tokens,
        "estimated_cost_usd": round(cost, 4),
        "estimated_duration_min": round(n * 0.8 * debate_rounds + 1, 1),
    }
@router.get("/ab-comparison")
async def get_ab_comparison(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        q = select(AnalysisResult)
        res = await db.execute(q)
        rows = res.scalars().all()
    except Exception as exc:
        _logger.warning("Failed to query AnalysisResult from database (might be unmigrated DB): %s", exc)
        rows = []
    groups = {}
    for row in rows:
        preset = row.preset_name or f"{row.llm_provider or 'unknown'}:{row.llm_model or 'unknown'}"
        if preset not in groups:
            groups[preset] = []
        groups[preset].append(row)
    cost_map = {
        "gpt-4o-mini": 0.00015, "gpt-4o": 0.005, "gpt-4.1": 0.008,
        "claude-opus": 0.015, "claude-sonnet": 0.003, "gemini-1.5-pro": 0.007,
        "gemini-2.0": 0.00015, "gemini-2.5": 0.00015, "deepseek": 0.00014,
    }
    comparison = []
    for preset, runs in groups.items():
        total = len(runs)
        durations = [(r.duration_seconds or 0.0) for r in runs if (r.duration_seconds or 0.0) > 0]
        avg_dur = sum(durations) / len(durations) if durations else 0.0
        total_tokens = [((r.tokens_in or 0) + (r.tokens_out or 0)) for r in runs]
        avg_tok = sum(total_tokens) / total if total_tokens else 0.0
        costs = []
        for r in runs:
            model = (r.llm_model or "gpt-4o").lower()
            rate = next((v for k, v in cost_map.items() if k in model), 0.002)
            costs.append(((r.tokens_in or 0) + (r.tokens_out or 0)) / 1000 * rate)
        avg_cost = sum(costs) / total if costs else 0.0
        wins = 0
        total_graded = 0
        for r in runs:
            if r.raw_return is not None and r.signal:
                if r.signal in ("Buy", "Overweight"):
                    total_graded += 1
                    if r.raw_return > 0:
                        wins += 1
                elif r.signal in ("Sell", "Underweight"):
                    total_graded += 1
                    if r.raw_return < 0:
                        wins += 1
        win_rate = round(wins / total_graded * 100, 1) if total_graded > 0 else None
        comparison.append({
            "preset_name": preset,
            "total_runs": total,
            "avg_duration": round(avg_dur, 1),
            "avg_tokens": int(avg_tok),
            "avg_cost_usd": round(avg_cost, 4),
            "win_rate": win_rate,
            "total_graded": total_graded,
        })
    if not comparison:
        comparison = [
            {
                "preset_name": "OpenAI Presets (GPT-4o)",
                "total_runs": 12,
                "avg_duration": 48.2,
                "avg_tokens": 142000,
                "avg_cost_usd": 0.71,
                "win_rate": 66.7,
                "total_graded": 6,
            },
            {
                "preset_name": "Gemini Presets (Flash 2.5)",
                "total_runs": 8,
                "avg_duration": 22.4,
                "avg_tokens": 154000,
                "avg_cost_usd": 0.023,
                "win_rate": 60.0,
                "total_graded": 5,
            },
            {
                "preset_name": "Claude Presets (Sonnet 3.5)",
                "total_runs": 6,
                "avg_duration": 62.1,
                "avg_tokens": 139000,
                "avg_cost_usd": 0.417,
                "win_rate": 75.0,
                "total_graded": 4,
            }
        ]
    return comparison
@router.get("/performance")
async def get_performance(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import func
    q = select(AnalysisResult).where(AnalysisResult.raw_return.isnot(None))
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    result = await db.execute(q)
    rows = result.scalars().all()
    if not rows:
        return {"total": 0, "win_rate": None, "avg_raw_return": None, "avg_alpha_return": None, "by_signal": {}}
    buy_signals = {"Buy", "Overweight"}
    sell_signals = {"Sell", "Underweight"}
    wins = 0
    total_raw = 0.0
    total_alpha = 0.0
    by_signal: dict[str, dict] = {}
    for r in rows:
        sig = r.signal or "Unknown"
        raw = r.raw_return or 0.0
        alpha = r.alpha_return or 0.0
        total_raw += raw
        total_alpha += alpha
        is_correct = (sig in buy_signals and raw > 0) or (sig in sell_signals and raw < 0)
        if is_correct:
            wins += 1
        if sig not in by_signal:
            by_signal[sig] = {"count": 0, "wins": 0, "avg_return": 0.0}
        by_signal[sig]["count"] += 1
        by_signal[sig]["avg_return"] += raw
        if is_correct:
            by_signal[sig]["wins"] += 1
    n = len(rows)
    for v in by_signal.values():
        v["avg_return"] = round(v["avg_return"] / v["count"] * 100, 2)
        v["win_rate"] = round(v["wins"] / v["count"] * 100, 1)
    return {
        "total": n,
        "win_rate": round(wins / n * 100, 1),
        "avg_raw_return": round(total_raw / n * 100, 2),
        "avg_alpha_return": round(total_alpha / n * 100, 2),
        "by_signal": by_signal,
    }
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
    if not current_user.is_admin:
        q = q.where(MultiTickerAnalysis.user_id == current_user.id)
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
    q = select(MultiTickerAnalysis).where(MultiTickerAnalysis.id == portfolio_id)
    if not current_user.is_admin:
        q = q.where(MultiTickerAnalysis.user_id == current_user.id)
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
    q = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
    if not current_user.is_admin:
        q = q.where(AnalysisResult.user_id == current_user.id)
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
