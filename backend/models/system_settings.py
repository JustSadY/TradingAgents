from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class SystemSettings(Base):
    """Global admin-only system settings (cron, webhook, etc.)."""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Watchlist cron automation
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    # Global watchlist for cron (JSON array of tickers)
    _watchlist: Mapped[str] = mapped_column("sys_watchlist", Text, default="[]")

    # Webhook notifications
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_events: Mapped[str] = mapped_column(Text, default='["analysis_complete"]')

    # Global data provider keys configured via Web UI
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

    import json as _json

    @property
    def watchlist(self) -> list[str]:
        import json
        return json.loads(self._watchlist or "[]")

    @watchlist.setter
    def watchlist(self, value: list[str]):
        import json
        self._watchlist = json.dumps(value)
