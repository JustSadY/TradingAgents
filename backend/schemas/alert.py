from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class AlertCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    condition: str = Field(..., pattern="^(above|below)$")
    target_price: float = Field(..., ge=0)
    auto_analyze: bool = False
    alert_type: str = Field(default="price", pattern="^(price|rsi|macd_cross)$")

class AlertUpdate(BaseModel):
    enabled: bool | None = None
    target_price: float | None = Field(default=None, gt=0)
    auto_analyze: bool | None = None

class AlertRead(BaseModel):
    id: int
    ticker: str
    alert_type: str
    condition: str
    target_price: float
    auto_analyze: bool
    creation_source: str
    enabled: bool
    triggered_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
