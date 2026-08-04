from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

class MultiTickerRunRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=10)
    trade_date: str
    asset_type: str = Field(default="stock", pattern="^(stock|crypto)$")

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        from backend.core.temporal import normalize_iso_date

        return normalize_iso_date(value, field_name="trade_date")

class MultiTickerRunResponse(BaseModel):
    task_id: str
    tickers: list[str]
    trade_date: str
    message: str = "Portfolio analysis started"

class MultiTickerListItem(BaseModel):
    id: int
    tickers: list[str]
    trade_date: str
    asset_type: str
    triggered_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MultiTickerResultRead(BaseModel):
    id: int
    tickers: list[str]
    trade_date: str
    asset_type: str
    analysis_ids: list[int]
    super_portfolio_report: str
    triggered_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
