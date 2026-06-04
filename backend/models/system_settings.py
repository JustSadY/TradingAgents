from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.core.database import Base
class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    searxng_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reddit_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reddit_client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reddit_user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alpha_vantage_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
