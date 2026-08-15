from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func

from backend.core.database import Base


class MarketDailySummary(Base):
    __tablename__ = "market_daily_summaries"
    __table_args__ = (Index("ix_market_daily_summaries_user_date", "user_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    tickers = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC))
