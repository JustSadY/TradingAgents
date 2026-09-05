from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, require_page
from backend.core.limiter import limiter
from backend.core.utils import safe_ticker_component
from backend.models.user import User
from backend.schemas.trading import (
    BacktestResponse,
    JournalDebriefResponse,
    JournalNoteReadResponse,
    JournalNoteResponse,
    OrderResponse,
    PerformanceResponse,
    PortfolioOptimizeRequest,
    PortfolioOptimizeResponse,
    PortfolioResponse,
    PortfolioStatsResponse,
    RebalanceResponse,
    ResetResponse,
    RiskDashboardResponse,
)
from backend.services import mock_trading_service as svc
from backend.services import trade_journal_service
from backend.services.backtest_service import run_backtest_simulation

router = APIRouter(prefix="/api/trading", tags=["trading"])

class APIOrderRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    action: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0, le=100_000)
    leverage: float = Field(default=1.0, ge=1.0, le=10.0)
    allow_short: bool = False
    analysis_id: int | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        try:
            return safe_ticker_component(v, max_len=20)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

class ResetRequest(BaseModel):
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)

class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    strategy_type: str = Field(..., pattern="^(macd_crossover|rsi_oversold|consensus)$")
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)
    slippage_bps: float = Field(default=5.0, ge=0, le=100)
    benchmark_ticker: str | None = Field(default=None, max_length=20)
    # Optional strategy tuning, normally supplied by the optimizer. The
    # simulation clamps these into its declared space, so an arbitrary payload
    # cannot reach an indicator; unknown keys are dropped.
    strategy_params: dict[str, float] | None = Field(default=None)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        try:
            return safe_ticker_component(v, max_len=20)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


    @model_validator(mode="after")
    def validate_date_window(self):
        from backend.core.temporal import validate_date_range

        try:
            self.start_date, self.end_date = validate_date_range(
                self.start_date, self.end_date, max_days=3650
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self
@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_page("trading")),
):
    return await svc.get_portfolio_with_live_prices(
        db,
        user=_,
        read_only=True,
        release_before_price_io=True,
    )

@router.post("/order", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    req: APIOrderRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_page("trading")),
):

    try:
        result = await svc.execute_order(
        db,
        ticker=req.ticker,
        action=req.action,
        quantity=req.quantity,
        analysis_id=req.analysis_id,
        user=_,
        leverage=req.leverage,
            allow_short=req.allow_short,
        )
    except svc.AnalysisOwnershipError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result

@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_page("trading")),
):
    return await svc.get_performance(db, user=_)

@router.post("/reset", response_model=ResetResponse)
async def reset_portfolio(
    req: ResetRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_page("trading")),
):
    result = await svc.reset_portfolio(db, initial_capital=req.initial_capital, user=_)
    return result

@router.post(
    "/backtest", response_model=BacktestResponse, responses={400: {"description": "Backtest simulation failed"}}
)
async def run_backtest(
    req: BacktestRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_page("backtest")),
):
    benchmark_ticker = req.benchmark_ticker
    if not benchmark_ticker:
        from backend.services.settings_service import get_or_create_settings

        user_settings = await get_or_create_settings(db, _)
        benchmark_ticker = getattr(user_settings, "benchmark_ticker", None) or "SPY"

    res = await run_backtest_simulation(
        db,
        ticker=req.ticker,
        strategy_type=req.strategy_type,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        user=_,
        slippage_bps=req.slippage_bps,
        benchmark_ticker=benchmark_ticker,
        strategy_params=req.strategy_params,
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.get("/portfolio-stats", response_model=PortfolioStatsResponse)
async def get_portfolio_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("performance")),
):
    from backend.services.portfolio_stats_service import get_portfolio_stats

    return await get_portfolio_stats(db, _)

@router.get("/risk-dashboard", response_model=RiskDashboardResponse)
async def get_risk_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("portfolio")),
):
    from backend.services.risk_dashboard_service import get_risk_dashboard

    return await get_risk_dashboard(db, _)

@router.post("/rebalance", response_model=RebalanceResponse)
@limiter.limit("5/hour")
async def rebalance_portfolio(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("portfolio")),
):
    from backend.services.portfolio_rebalance_service import get_rebalance_suggestions

    return await get_rebalance_suggestions(db, _)

@router.post("/portfolio/optimize", response_model=PortfolioOptimizeResponse)
@limiter.limit("10/hour")
async def optimize_portfolio(
    request: Request,
    req: PortfolioOptimizeRequest,
    _: User = Depends(require_page("portfolio")),
):
    from backend.services.portfolio_optimizer_service import OptimizerError, optimize_weights_async

    for ticker in req.tickers:
        safe_ticker_component(ticker)

    try:
        return await optimize_weights_async(
            req.tickers,
            datetime.now(UTC).strftime("%Y-%m-%d"),
            objective=req.objective,
            total_value=req.total_value,
            risk_aversion=req.risk_aversion,
        )
    except OptimizerError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

class JournalNoteRequest(BaseModel):
    note: str = Field(..., max_length=2000)

@router.post("/journal/{order_id}/note", response_model=JournalNoteResponse, status_code=200)
async def save_trade_note(
    order_id: int,
    req: JournalNoteRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("orders")),
):
    try:
        return await trade_journal_service.save_note(db, _, order_id, req.note)
    except trade_journal_service.TradeJournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

@router.get("/journal/{order_id}", response_model=JournalNoteReadResponse)
async def get_trade_note(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("orders")),
):
    result = await trade_journal_service.get_note(db, _, order_id)
    return result or {"order_id": order_id, "note": "", "ai_debrief": None, "has_debrief": False}

@router.post("/journal/{order_id}/debrief", response_model=JournalDebriefResponse)
@limiter.limit("10/hour")
async def generate_trade_debrief(
    request: Request,
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_page("orders")),
):
    try:
        return await trade_journal_service.generate_debrief(db, _, order_id)
    except trade_journal_service.TradeJournalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
