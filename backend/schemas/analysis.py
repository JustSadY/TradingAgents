import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

_CANONICAL_SIGNALS = frozenset({"Buy", "Overweight", "Hold", "Underweight", "Sell"})

def _validated_signal(value: object) -> str | None:
    """Expose only the canonical analysis signal enum through the API.

    Database migrations canonicalize known historical spellings.  Values
    outside the enum remain hidden rather than leaking an invalid contract to
    frontend consumers.
    """
    if value is None:
        return None
    if isinstance(value, str) and value in _CANONICAL_SIGNALS:
        return value
    logger.warning("Analysis signal: unexpected value %r — coercing to None", value)
    return None

class AnalysisRunRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    trade_date: str
    asset_type: str = Field(default="stock", pattern="^(stock|crypto)$")

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        from backend.core.temporal import normalize_iso_date

        return normalize_iso_date(value, field_name="trade_date")

class AnalysisRunResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    message: str = "Analysis started"

class AnalysisResultRead(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    macro_report: str
    options_report: str
    quant_report: str
    earnings_report: str
    insider_report: str = ""
    ownership_report: str = ""
    ratings_report: str = ""
    short_interest_report: str = ""
    valuation_report: str = ""
    catalyst_report: str = ""
    review_report: str
    synthesis_report: str = ""
    audit_report: str = ""
    agent_qa_report: str = ""
    investment_plan: str
    analysis_plan_json: Any = None
    synthesis_json: Any = None
    market_regime_json: Any = None
    strategy_before_json: Any = None
    strategy_after_json: Any = None
    strategy_candidate_json: Any = None
    pm_proposal_json: Any = None
    portfolio_decision_json: Any = None
    decision_transition_json: Any = None
    calibrated_confidence: float | None = None
    strategy_update_status: str | None = None
    strategy_id: int | None = None
    strategy_before_version: int | None = None
    strategy_after_version: int | None = None
    analysis_mode: str = "live"
    learning_eligible: bool = True
    trader_plan: str
    final_decision: str
    bull_history: Any = None
    bear_history: Any = None
    investment_debate_history: Any = None
    risk_debate_history: Any = None
    judge_decision: str = ""
    trader_proposal_json: str = "{}"
    chart_annotations: Any = None
    risk_metrics: Any = None
    quality: Any = None
    degraded: bool = False
    failed_agents: list[str] | None = None
    llm_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    estimated_cost_usd: float = 0.0
    llm_provider: str | None = None
    llm_model: str | None = None
    preset_name: str | None = None
    duration_seconds: float
    triggered_by: str
    created_at: datetime
    raw_return: float | None = None
    alpha_return: float | None = None
    holding_days: int | None = None

    @field_validator("signal", mode="before")
    @classmethod
    def validate_signal(cls, v: object) -> str | None:
        return _validated_signal(v)

    @field_validator("failed_agents", mode="before")
    @classmethod
    def coerce_failed_agents(cls, v: object) -> object:
        if isinstance(v, str):
            if v == "":
                return None
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v

    model_config = ConfigDict(from_attributes=True)

class AnalysisListItem(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    duration_seconds: float
    triggered_by: str
    created_at: datetime
    chart_annotations: Any = None
    llm_provider: str | None = None
    llm_model: str | None = None
    preset_name: str | None = None

    @field_validator("signal", mode="before")
    @classmethod
    def validate_signal(cls, v: object) -> str | None:
        return _validated_signal(v)

    model_config = ConfigDict(from_attributes=True)


class AssetStrategyRead(BaseModel):
    id: int
    ticker: str
    asset_type: str
    status: str
    version: int
    strategic_bias: str
    conviction: float
    accepted_rating: str | None = None
    thesis: str
    key_drivers: Any = None
    watch_conditions: Any = None
    invalidation_conditions: Any = None
    open_questions: Any = None
    regime_assumption: Any = None
    time_horizon: str | None = None
    last_analysis_id: int | None = None
    effective_at: datetime | None = None
    recorded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_reviewed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AssetStrategyVersionRead(BaseModel):
    id: int
    strategy_id: int
    version: int
    analysis_id: int | None = None
    revision_action: str
    before_state: Any = None
    after_state: Any = None
    triggered_invalidations: Any = None
    supporting_evidence: Any = None
    regime_before: Any = None
    regime_after: Any = None
    pm_proposed_rating: str | None = None
    accepted_rating: str | None = None
    change_strength: float | None = None
    effective_at: datetime | None = None
    recorded_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ChatMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)

class ActiveTaskRead(BaseModel):
    task_id: str
    ticker: str | None = None
    trade_date: str | None = None
    asset_type: str | None = None
    user_id: int | None = None
    started_at: float | None = None
    status: str | None = None

class CancelTaskResponse(BaseModel):
    cancelled: bool
    task_id: str

class CostEstimateResponse(BaseModel):
    analyst_count: int
    estimated_tokens: int
    estimated_cost_usd: float
    estimated_duration_min: float
    pricing_source: str
    pricing_is_fallback: bool

class ABComparisonItem(BaseModel):
    preset_name: str
    total_runs: int
    avg_duration: float
    avg_tokens: int
    avg_cost_usd: float
    win_rate: float | None
    total_graded: int
    win_rate_last_50: float | None
    avg_alpha_last_50: float
    avg_raw_return_last_50: float
    total_graded_last_50: int

class BySignalItem(BaseModel):
    count: int
    wins: int
    avg_return: float
    win_rate: float

class PerformanceResponse(BaseModel):
    total: int
    win_rate: float | None
    avg_raw_return: float | None
    avg_alpha_return: float | None
    by_signal: dict[str, BySignalItem]

class AnalystAttributionItem(BaseModel):
    key: str
    label: str
    total_predictions: int
    correct_predictions: int
    win_rate: float
    weight: float
    chronic_underperformer: bool

class PerformanceAttributionResponse(BaseModel):
    attribution: list[AnalystAttributionItem]
    total_evaluated_runs: int

class CheckpointItem(BaseModel):
    checkpoint_id: str
    step: int
    node: str
    label: str
    ts: str

_TIME_TRAVEL_ALLOWED_FIELDS = frozenset({
    "messages",
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "macro_report",
    "options_report",
    "quant_report",
    "earnings_report",
    "insider_report",
    "ownership_report",
    "ratings_report",
    "short_interest_report",
    "valuation_report",
    "catalyst_report",
    "review_report",
    "synthesis_report",
    "audit_report",
    "agent_qa_report",
    "investment_plan",
    "analysis_plan_json",
    "synthesis_json",
    "market_regime_json",
    "strategy_candidate_json",
    "pm_proposal_json",
    "investment_debate_state",
    "risk_debate_state",
    "portfolio_decision_json",
    "decision_transition_json",
    "calibrated_confidence",
    "final_trade_decision",
    "final_signal",
    "trader_investment_plan",
    "trader_proposal_json",
})
_TIME_TRAVEL_PROTECTED_FIELDS = frozenset({
    "company_of_interest", "ticker", "trade_date", "asset_type", "user_id",
    "task_id", "checkpoint_scope",
})


class TimeTravelRequest(BaseModel):
    checkpoint_id: str = Field(..., min_length=1, max_length=256)
    update_state: dict = Field(default_factory=dict)

    @field_validator("update_state")
    @classmethod
    def validate_update_state(cls, value: dict) -> dict:
        import json

        if not isinstance(value, dict):
            raise ValueError("update_state must be an object")
        protected = sorted(set(value) & _TIME_TRAVEL_PROTECTED_FIELDS)
        if protected:
            raise ValueError(f"protected state fields cannot be changed: {', '.join(protected)}")
        unsupported = sorted(set(value) - _TIME_TRAVEL_ALLOWED_FIELDS)
        if unsupported:
            raise ValueError(f"unsupported state fields: {', '.join(unsupported)}")
        # This endpoint is a rollback/reset control, not a generic state editor.
        # Only empty values may clear stale downstream outputs before replay.
        invalid_values = []
        for key, item in value.items():
            is_empty = item is None or item == "" or item == "{}" or item == [] or item == {}
            if not is_empty:
                invalid_values.append(key)
        if invalid_values:
            raise ValueError(
                "time-travel fields may only be reset to empty values: " + ", ".join(sorted(invalid_values))
            )
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded.encode("utf-8")) > 128_000:
            raise ValueError("update_state payload is too large")
        return value

class TimeTravelResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
