from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Global Server Configuration
    trading_mode: Mapped[str] = mapped_column(String(20), default="simulation")
    active_broker: Mapped[str] = mapped_column(String(50), default="simulation")
    active_data_vendor: Mapped[str] = mapped_column(String(50), default="yfinance")
    # Data-vendor routing is a server-level concern (which provider the engine
    # queries), so it lives here (global) rather than per-user in app_settings.
    data_vendor_core_stock: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_technicals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_fundamentals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_news: Mapped[str] = mapped_column(String(50), default="yfinance")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
