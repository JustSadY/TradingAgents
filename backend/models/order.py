from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import MONEY, Base

if TYPE_CHECKING:
    from backend.models.portfolio import Portfolio
    from backend.models.trade_note import TradeNote


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_portfolio_ticker", "portfolio_id", "ticker"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True)
    broker: Mapped[str] = mapped_column(String(50), nullable=False)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity_requested: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    quantity_filled: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    status: Mapped[str] = mapped_column(String(30), default="PENDING", index=True)
    price_per_share: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    total_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    commission: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    # Leverage applied to this order (1.0 = spot/cash). 'side' records the
    # position direction; 'realized_pnl' is populated when an order closes a
    # position (SELL/liquidation), otherwise 0.
    leverage: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("1.0"))
    side: Mapped[str] = mapped_column(String(5), default="long")
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    analysis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("analysis_results.id", ondelete="SET NULL"), nullable=True, index=True)
    ai_signal: Mapped[str] = mapped_column(String(50), default="")
    ai_reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    portfolio: Mapped["Portfolio"] = relationship("Portfolio", back_populates="orders")
    trade_notes: Mapped[list["TradeNote"]] = relationship("TradeNote", back_populates="order", cascade="all, delete-orphan")
