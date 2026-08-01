from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import MONEY, Base

class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        Index("ix_price_alerts_enabled_triggered", "enabled", "triggered_at"),
        Index("ix_price_alerts_user_ticker", "user_id", "ticker"),
        Index("ix_price_alerts_user_enabled", "user_id", "enabled"),
        Index("ix_price_alerts_user_source_run", "user_id", "creation_source", "creation_run_id"),
        Index(
            "ix_price_alerts_ai_equivalence",
            "user_id",
            "creation_source",
            "ticker",
            "condition",
            "alert_type",
            "created_at",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(20), default="price", server_default="price")
    condition: Mapped[str] = mapped_column(String(10), nullable=False)
    target_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    auto_analyze: Mapped[bool] = mapped_column(Boolean, default=False)
    creation_source: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual", nullable=False)
    creation_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
