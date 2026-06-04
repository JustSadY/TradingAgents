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
    trading_mode: Mapped[str] = mapped_column(String(20), default="simulation")
    active_broker: Mapped[str] = mapped_column(String(50), default="simulation")
    active_data_vendor: Mapped[str] = mapped_column(String(50), default="yfinance")
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=0.5)
    _watchlist: Mapped[str] = mapped_column("watchlist", Text, default='[]')
    _selected_analysts: Mapped[str] = mapped_column(
        "selected_analysts",
        Text,
        default='["market", "news", "fundamentals", "social"]',
    )
    llm_provider: Mapped[str] = mapped_column(String(50), default="openai")
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    backend_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    openai_reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    anthropic_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    google_thinking_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    output_language: Mapped[str] = mapped_column(String(50), default="English")
    investor_persona: Mapped[str] = mapped_column(String(50), default="conservative")
    analyst_concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    checkpoint_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_recur_limit: Mapped[int] = mapped_column(Integer, default=1000)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    azure_deployment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_vendor_core_stock: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_technicals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_fundamentals: Mapped[str] = mapped_column(String(50), default="yfinance")
    data_vendor_news: Mapped[str] = mapped_column(String(50), default="yfinance")
    max_debate_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_risk_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_position_size_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)
    include_historical_analyses: Mapped[bool] = mapped_column(Boolean, default=False)
    historical_analyses_limit: Mapped[int] = mapped_column(Integer, default=5)
    strict_backtest_learning: Mapped[bool] = mapped_column(Boolean, default=True)
    _analyst_models: Mapped[str] = mapped_column("analyst_models", Text, default='{}')
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
    @property
    def selected_analysts(self) -> list[str]:
        return json.loads(self._selected_analysts or '[]')
    @selected_analysts.setter
    def selected_analysts(self, value: list[str]):
        self._selected_analysts = json.dumps(value)
    @property
    def analyst_models(self) -> dict[str, str]:
        return json.loads(self._analyst_models or '{}')
    @analyst_models.setter
    def analyst_models(self, value: dict[str, str]):
        self._analyst_models = json.dumps(value)
