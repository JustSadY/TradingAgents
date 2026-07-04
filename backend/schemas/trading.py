from pydantic import BaseModel


class AutoCloseRecord(BaseModel):
    ticker: str
    reason: str
    side: str
    price: float
    realized_pnl: float


class HoldingItem(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: float
    side: str
    leverage: float
    market_value: float
    equity: float
    borrowed_amount: float
    margin_used: float
    liquidation_price: float
    stop_loss: float
    take_profit: float
    unrealized_pnl: float
    pnl_pct: float


class PortfolioResponse(BaseModel):
    id: int
    mode: str
    initial_capital: float
    cash_available: float
    margin_used: float
    positions_value: float
    total_value: float
    total_pnl: float
    total_pnl_pct: float
    holdings: list[HoldingItem] = []
    auto_closes: list[AutoCloseRecord] = []
    liquidations: list[AutoCloseRecord] = []


class PerformanceResponse(PortfolioResponse):
    benchmark_ticker: str | None = None
    benchmark_return_pct: float | None = None
    alpha_pct: float | None = None


class OrderResponse(BaseModel):
    order_id: int
    ticker: str
    action: str
    side: str
    quantity: float
    price: float
    leverage: float
    total_value: float
    commission: float
    realized_pnl: float
    status: str


class ResetResponse(BaseModel):
    status: str
    message: str


class BacktestTradeRecord(BaseModel):
    entry_date: str
    exit_date: str
    side: str
    entry_price: float
    exit_price: float
    return_pct: float
    pnl: float
    reason: str


class BacktestEquityPoint(BaseModel):
    date: str
    value: float
    cash: float
    holdings_value: float


class BacktestBenchmark(BaseModel):
    ticker: str
    return_pct: float


class BacktestResponse(BaseModel):
    initial_capital: float
    final_value: float
    total_return: float
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    trades_count: int
    trades: list[BacktestTradeRecord] = []
    equity_curve: list[BacktestEquityPoint] = []
    slippage_bps: float
    benchmark: BacktestBenchmark | None = None
    alpha_pct: float | None = None


class TradeSummaryRecord(BaseModel):
    ticker: str
    pnl_pct: float
    date: str | None = None


class TickerBreakdownRecord(BaseModel):
    ticker: str
    trades: int
    wins: int
    win_rate: float
    total_pnl: float


class PortfolioStatsResponse(BaseModel):
    total_trades: int
    winning_trades: int
    win_rate: float
    avg_return_pct: float | None = None
    best_trade: TradeSummaryRecord | None = None
    worst_trade: TradeSummaryRecord | None = None
    total_realized_pnl: float
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    by_ticker: list[TickerBreakdownRecord] = []


class SectorWeight(BaseModel):
    sector: str
    weight_pct: float


class CorrelationPair(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: float


class HoldingRisk(BaseModel):
    ticker: str
    weight_pct: float
    volatility_annual: float | None = None
    beta: float | None = None
    sector: str


class RiskBreach(BaseModel):
    type: str
    value: float
    threshold: float
    sector: str | None = None


class RiskDashboardResponse(BaseModel):
    beta: float | None = None
    volatility: float | None = None
    sector_weights: list[SectorWeight] = []
    correlation: list[CorrelationPair] = []
    holdings_risk: list[HoldingRisk] = []
    breaches: list[RiskBreach] = []
    message: str | None = None


class RebalanceSuggestion(BaseModel):
    action: str
    ticker: str
    quantity: float
    rationale: str
    urgency: str


class RebalanceResponse(BaseModel):
    summary: str
    score: int
    issues: list[str] = []
    suggestions: list[RebalanceSuggestion] = []


class JournalNoteResponse(BaseModel):
    order_id: int
    note: str
    has_debrief: bool


class JournalNoteReadResponse(BaseModel):
    order_id: int
    note: str
    ai_debrief: str | None = None
    has_debrief: bool


class JournalDebriefResponse(BaseModel):
    order_id: int
    ai_debrief: str
