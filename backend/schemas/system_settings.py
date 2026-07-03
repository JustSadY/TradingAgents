from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingsRead(BaseModel):
    id: int = 1
    trading_mode: str = "simulation"
    active_broker: str = "simulation"
    active_data_vendor: str = "yfinance"
    data_vendor_core_stock: str = "yfinance"
    data_vendor_technicals: str = "yfinance"
    data_vendor_fundamentals: str = "yfinance"
    data_vendor_news: str = "yfinance"

    node_retry_attempts: int = 2
    node_retry_base_delay: float = 1.0
    node_timeout_seconds: int = 120
    tool_timeout_seconds: int = 60
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown: int = 60
    stall_timeout_seconds: int = 120

    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SystemSettingsUpdate(BaseModel):
    trading_mode: str | None = None
    active_broker: str | None = None
    active_data_vendor: str | None = None
    data_vendor_core_stock: str | None = None
    data_vendor_technicals: str | None = None
    data_vendor_fundamentals: str | None = None
    data_vendor_news: str | None = None

    node_retry_attempts: int | None = Field(default=None, ge=1, le=10)
    node_retry_base_delay: float | None = Field(default=None, ge=0.1, le=10)
    node_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    tool_timeout_seconds: int | None = Field(default=None, ge=15, le=300)
    circuit_breaker_threshold: int | None = Field(default=None, ge=1, le=20)
    circuit_breaker_cooldown: int | None = Field(default=None, ge=10, le=600)
    stall_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
