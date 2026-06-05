import json
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.core.database import Base
def _json_default(value: Any) -> str:
    return json.dumps(value)
class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=0.5)
    _watchlist: Mapped[str] = mapped_column("watchlist", Text, default='[]')
    output_language: Mapped[str] = mapped_column(String(50), default="English")
    llm_provider: Mapped[str] = mapped_column(String(50), default="openai")
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    investor_persona: Mapped[str] = mapped_column(String(50), default="conservative")
    analyst_concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    max_recur_limit: Mapped[int] = mapped_column(Integer, default=1000)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    openai_reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    anthropic_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    google_thinking_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    max_debate_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_risk_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_position_size_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)
    strict_stop_loss_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    include_historical_analyses: Mapped[bool] = mapped_column(Boolean, default=False)
    historical_analyses_limit: Mapped[int] = mapped_column(Integer, default=5)
    strict_backtest_learning: Mapped[bool] = mapped_column(Boolean, default=True)
    node_retry_attempts: Mapped[int] = mapped_column(Integer, default=2)
    node_retry_base_delay: Mapped[float] = mapped_column(Float, default=1.0)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_events: Mapped[str] = mapped_column(Text, default='["analysis_complete"]')
    active_preset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    @property
    def watchlist(self) -> list[str]:
        return json.loads(self._watchlist or "[]")
    @watchlist.setter
    def watchlist(self, value: list[str]):
        self._watchlist = json.dumps(value)

