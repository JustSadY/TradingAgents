from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SettingsBase(BaseModel):
    cron_enabled: bool = False
    cron_schedule: str = "0 9 * * 1-5"
    price_tolerance_pct: float = 0.5
    watchlist: list[str] = []
    output_language: str = "English"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    investor_persona: str = "conservative"
    analyst_concurrency_limit: int = 1
    max_recur_limit: int = 1000
    benchmark_ticker: Optional[str] = None
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
    max_position_size_pct: float = 10.0
    max_risk_per_trade_pct: float = 2.0
    strict_stop_loss_mode: bool = False
    include_historical_analyses: bool = False
    historical_analyses_limit: int = 5
    strict_backtest_learning: bool = True
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    google_thinking_level: Optional[str] = None
    node_retry_attempts: int = 2
    node_retry_base_delay: float = 1.0
    webhook_url: Optional[str] = None
    webhook_enabled: bool = False
    webhook_events: str = '["analysis_complete"]'
    active_preset_name: Optional[str] = None


class SettingsRead(SettingsBase):
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    # We explicitly define these to keep the validation logic (ge, le)
    cron_enabled: Optional[bool] = None
    cron_schedule: Optional[str] = None
    price_tolerance_pct: Optional[float] = Field(default=None, ge=0, le=50)
    watchlist: Optional[list[str]] = None
    output_language: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    investor_persona: Optional[str] = None
    analyst_concurrency_limit: Optional[int] = Field(default=None, ge=1, le=16)
    max_recur_limit: Optional[int] = Field(default=None, ge=100, le=5000)
    benchmark_ticker: Optional[str] = None
    max_debate_rounds: Optional[int] = Field(default=None, ge=1, le=10)
    max_risk_rounds: Optional[int] = Field(default=None, ge=1, le=10)
    max_position_size_pct: Optional[float] = Field(default=None, ge=1, le=100)
    max_risk_per_trade_pct: Optional[float] = Field(default=None, ge=0.1, le=50)
    strict_stop_loss_mode: Optional[bool] = None
    include_historical_analyses: Optional[bool] = None
    historical_analyses_limit: Optional[int] = Field(default=None, ge=1, le=50)
    strict_backtest_learning: Optional[bool] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    google_thinking_level: Optional[str] = None
    node_retry_attempts: Optional[int] = Field(default=None, ge=1, le=10)
    node_retry_base_delay: Optional[float] = Field(default=None, ge=0.1, le=10.0)
    webhook_url: Optional[str] = None
    webhook_enabled: Optional[bool] = None
    webhook_events: Optional[str] = None
    active_preset_name: Optional[str] = None
