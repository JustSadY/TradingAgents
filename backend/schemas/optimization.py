"""Request/response contracts for strategy parameter optimization."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.utils import safe_ticker_component


class OptimizationRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    # `consensus` is deliberately absent: it replays stored analyses and has no
    # tunable parameters, so there is nothing for a search to explore.
    strategy_type: str = Field(..., pattern="^(macd_crossover|rsi_oversold)$")
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    objective: str = Field(default="sharpe_ratio", pattern="^(sharpe_ratio|total_return|calmar|win_rate)$")
    n_trials: int = Field(default=40, ge=1, le=200)
    initial_capital: float = Field(default=100_000.0, gt=0, le=10_000_000)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        try:
            return safe_ticker_component(v.upper(), max_len=20)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def validate_date_window(self):
        from backend.core.temporal import validate_date_range

        self.start_date, self.end_date = validate_date_range(self.start_date, self.end_date, max_days=3650)
        return self


class OptimizationTrialRead(BaseModel):
    number: int
    params: dict
    value: float | None = None
    metrics: dict = Field(default_factory=dict)
    state: str


class OptimizationRunRead(BaseModel):
    id: int
    ticker: str
    strategy_type: str
    objective: str
    start_date: str
    end_date: str
    trials_requested: int
    trials_completed: int
    status: str
    best_params: dict | None = None
    best_value: float | None = None
    best_metrics: dict | None = None
    baseline_params: dict | None = None
    baseline_value: float | None = None
    baseline_metrics: dict | None = None
    trials: list[dict] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OptimizationParamSpec(BaseModel):
    type: str
    default: float
    min: float
    max: float


class OptimizationCatalogEntry(BaseModel):
    label: str
    params: dict[str, OptimizationParamSpec]


class OptimizationCatalog(BaseModel):
    """What can be optimized, and against which objectives."""

    strategies: dict[str, OptimizationCatalogEntry]
    objectives: dict[str, str]
    max_trials: int
    default_trials: int
