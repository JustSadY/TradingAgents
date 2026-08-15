import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class MultiTickerAnalysis(Base):
    __tablename__ = "multi_ticker_analyses"
    __table_args__ = (
        Index("ix_multi_ticker_analyses_user_trade_date", "user_id", "trade_date"),
        Index("ix_multi_ticker_analyses_user_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    trade_date: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock")
    _tickers: Mapped[str] = mapped_column("tickers", Text, default="[]")
    _analysis_ids: Mapped[str] = mapped_column("analysis_ids", Text, default="[]")
    super_portfolio_report: Mapped[str] = mapped_column(Text, default="")
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )

    @property
    def tickers(self) -> list[str]:
        return json.loads(self._tickers or "[]")

    @tickers.setter
    def tickers(self, value: list[str]):
        self._tickers = json.dumps(value)

    @property
    def analysis_ids(self) -> list[int]:
        return json.loads(self._analysis_ids or "[]")

    @analysis_ids.setter
    def analysis_ids(self, value: list[int]):
        self._analysis_ids = json.dumps(value)
