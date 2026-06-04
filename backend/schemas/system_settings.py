from datetime import datetime
from pydantic import BaseModel


class SystemSettingsRead(BaseModel):
    searxng_url: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    alpha_vantage_api_key: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SystemSettingsUpdate(BaseModel):
    searxng_url: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str | None = None
    alpha_vantage_api_key: str | None = None
