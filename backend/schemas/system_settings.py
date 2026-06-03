from datetime import datetime
from pydantic import BaseModel


class SystemSettingsRead(BaseModel):
    cron_enabled: bool
    cron_schedule: str
    watchlist: list[str]
    webhook_url: str | None = None
    webhook_enabled: bool
    webhook_events: str
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    cron_enabled: bool | None = None
    cron_schedule: str | None = None
    watchlist: list[str] | None = None
    webhook_url: str | None = None
    webhook_enabled: bool | None = None
    webhook_events: str | None = None
