from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.core.database import Base

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    
    # Global Server Configuration
    trading_mode: Mapped[str] = mapped_column(String(20), default="simulation")
    active_broker: Mapped[str] = mapped_column(String(50), default="simulation")
    active_data_vendor: Mapped[str] = mapped_column(String(50), default="yfinance")
    checkpoint_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    include_historical_analyses: Mapped[bool] = mapped_column(Boolean, default=False)
    historical_analyses_limit: Mapped[int] = mapped_column(Integer, default=5)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
