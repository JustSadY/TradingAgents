from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SystemSettingsRead(BaseModel):
    id: int = 1
    trading_mode: str = "simulation"
    active_broker: str = "simulation"
    active_data_vendor: str = "yfinance"
    data_vendor_core_stock: str = "yfinance"
    data_vendor_technicals: str = "yfinance"
    data_vendor_fundamentals: str = "yfinance"
    data_vendor_news: str = "yfinance"

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
