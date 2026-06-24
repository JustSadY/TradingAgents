from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import MONEY, Base

if TYPE_CHECKING:
    from backend.models.order import Order


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("user_id", "mode", name="uq_portfolio_user_mode"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    broker: Mapped[str] = mapped_column(String(50), nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_available: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    holdings: Mapped[list["Holding"]] = relationship("Holding", back_populates="portfolio")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="portfolio")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "ticker", name="uq_holding_portfolio_ticker"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    avg_buy_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    side: Mapped[str] = mapped_column(String(5), default="long")
    leverage: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("1.0"))
    margin_used: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    borrowed_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    liquidation_price: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    interest_accrued: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    stop_loss: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    take_profit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.0"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    portfolio: Mapped[Portfolio] = relationship("Portfolio", back_populates="holdings")
