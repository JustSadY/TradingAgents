from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HoldingRead(BaseModel):
    id: int
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: float
    unrealized_pnl: float
    side: str = "long"
    leverage: float = 1.0
    margin_used: float = 0.0
    borrowed_amount: float = 0.0
    liquidation_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    updated_at: datetime
    opened_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class PortfolioRead(BaseModel):
    id: int
    mode: str
    broker: str
    initial_capital: float
    current_balance: float
    cash_available: float
    status: str
    holdings: list[HoldingRead]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class CorrelationResponse(BaseModel):
    tickers: list[str]
    #: Square correlation matrix, row-aligned with ``tickers``. Pandas yields
    #: NaN wherever two series share no overlapping dates, and that serialises
    #: to null rather than a number.
    matrix: list[list[float | None]]
    avg_correlation: float | None
    warning: str | None

class OrderRead(BaseModel):
    id: int
    portfolio_id: int
    broker: str
    ticker: str
    action: str
    quantity_requested: float
    quantity_filled: float
    status: str
    price_per_share: float | None
    total_value: float | None
    commission: float
    leverage: float = 1.0
    side: str = "long"
    realized_pnl: float = 0.0
    external_order_id: str | None
    analysis_id: int | None
    ai_signal: str
    created_at: datetime
    executed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
