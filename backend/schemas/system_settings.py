from datetime import datetime
from pydantic import BaseModel


class SystemSettingsRead(BaseModel):
    id: int = 1
    trading_mode: str = "simulation"
    active_broker: str = "simulation"
    active_data_vendor: str = "yfinance"
    checkpoint_enabled: bool = False
    include_historical_analyses: bool = False
    historical_analyses_limit: int = 5
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    trading_mode: str | None = None
    active_broker: str | None = None
    active_data_vendor: str | None = None
    checkpoint_enabled: bool | None = None
    include_historical_analyses: bool | None = None
    historical_analyses_limit: int | None = None
