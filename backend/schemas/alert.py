from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.utils import safe_ticker_component


class AlertCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    condition: str = Field(..., pattern="^(above|below)$")
    target_price: float = Field(default=0.0, ge=0)
    auto_analyze: bool = False
    alert_type: str = Field(default="price", pattern="^(price|rsi|macd_cross)$")

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        return safe_ticker_component(value.upper().strip(), max_len=20)

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.alert_type == "price" and self.target_price <= 0:
            raise ValueError("Price alerts require a positive target_price")
        if self.alert_type == "rsi" and not 0 <= self.target_price <= 100:
            raise ValueError("RSI threshold must be between 0 and 100")
        if self.alert_type == "macd_cross":
            self.target_price = 0.0
        return self

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
