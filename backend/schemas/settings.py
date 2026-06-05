from datetime import datetime
from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    cron_enabled: bool
    cron_schedule: str
    price_tolerance_pct: float
    watchlist: list[str]
    selected_analysts: list[str]
    output_language: str = "English"
    investor_persona: str = "conservative"
    analyst_concurrency_limit: int = 1
    max_recur_limit: int = 1000
    benchmark_ticker: str | None = None
    max_debate_rounds: int
    max_risk_rounds: int
    max_position_size_pct: float
    max_risk_per_trade_pct: float
    strict_stop_loss_mode: bool = False
    include_historical_analyses: bool = False
    historical_analyses_limit: int = 5
    strict_backtest_learning: bool = True
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int = 2
    node_retry_base_delay: float = 1.0
    webhook_url: str | None = None
    webhook_enabled: bool = False
    webhook_events: str = '["analysis_complete"]'
    active_preset_name: str | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    cron_enabled: bool | None = None
    cron_schedule: str | None = None
    price_tolerance_pct: float | None = Field(default=None, ge=0, le=50)
    watchlist: list[str] | None = None
    selected_analysts: list[str] | None = None
    output_language: str | None = None
    investor_persona: str | None = None
    analyst_concurrency_limit: int | None = Field(default=None, ge=1, le=16)
    max_recur_limit: int | None = Field(default=None, ge=100, le=5000)
    benchmark_ticker: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1, le=10)
    max_risk_rounds: int | None = Field(default=None, ge=1, le=10)
    max_position_size_pct: float | None = Field(default=None, ge=1, le=100)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=50)
    strict_stop_loss_mode: bool | None = None
    include_historical_analyses: bool | None = None
    historical_analyses_limit: int | None = Field(default=None, ge=1, le=50)
    strict_backtest_learning: bool | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int | None = Field(default=None, ge=1, le=10)
    node_retry_base_delay: float | None = Field(default=None, ge=0.1, le=10.0)
    webhook_url: str | None = None
    webhook_enabled: bool | None = None
    webhook_events: str | None = None
    active_preset_name: str | None = None
