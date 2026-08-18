from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class OptimizationRun(Base):
    """One parameter search over the backtest, and what it found.

    Kept because a search is expensive — tens of full backtests — and its value
    is the parameter set at the end, which an operator wants to look up later
    and re-run the ordinary backtest with.
    """

    __tablename__ = "optimization_runs"
    __table_args__ = (
        Index("ix_optimization_runs_user_created", "user_id", "created_at"),
        Index("ix_optimization_runs_user_ticker", "user_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    objective: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[str] = mapped_column(String(20), nullable=False)
    end_date: Mapped[str] = mapped_column(String(20), nullable=False)
    trials_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trials_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)

    best_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    best_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Full trial history, so a search can be inspected rather than only trusted.
    trials: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
