from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.constants import WEBHOOK_EVENTS
from backend.schemas.common import ApiResponse
from backend.trading_agents.config import MAX_FALLBACK_LLM_CHAIN_LENGTH, FallbackLLMConfig

_MAX_WATCHLIST_ITEMS = 100
_MAX_TICKER_LENGTH = 20


def _normalize_watchlist(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if len(value) > _MAX_WATCHLIST_ITEMS:
        raise ValueError(f"watchlist cannot contain more than {_MAX_WATCHLIST_ITEMS} symbols")
    normalized: list[str] = []
    for raw in value:
        ticker = str(raw).strip().upper()
        if not ticker or len(ticker) > _MAX_TICKER_LENGTH:
            raise ValueError("watchlist contains an invalid ticker")
        if not all(ch.isalnum() or ch in ".-^=" for ch in ticker):
            raise ValueError(f"Unsupported ticker format: {ticker}")
        if ticker not in normalized:
            normalized.append(ticker)
    return normalized


def _validate_webhook_url_shape(v: str | None) -> str | None:
    """Shared shape check for the ``webhook_url`` field on both settings models.

    This only validates it's a well-formed http(s) URL — it can't do the DNS
    resolution needed to catch SSRF targets (localhost, 169.254.169.254,
    RFC1918 ranges). That check runs separately at the actual save path via
    ``notification_service.resolve_webhook_target``.
    """
    if v is None or v == "":
        return v
    from urllib.parse import urlparse

    try:
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("webhook_url must be a valid http or https URL")
    except Exception as exc:
        raise ValueError("webhook_url must be a valid http or https URL") from exc
    return v


def _normalize_webhook_events(events: list[str]) -> list[str]:
    """Validate the canonical webhook-event collection.

    ``webhook_events`` used to be a comma-separated JSON string.  The API now
    exposes a real list, so whitespace, duplicates, phantom event names, and
    non-list values never reach persistence or the delivery path.
    """
    normalized: list[str] = []
    unknown: list[str] = []
    for event in events:
        name = event.strip()
        if name not in WEBHOOK_EVENTS:
            unknown.append(name or "<empty>")
            continue
        if name not in normalized:
            normalized.append(name)
    if unknown:
        raise ValueError(f"Unsupported webhook events: {', '.join(unknown)}")
    return normalized


class SettingsBase(BaseModel):
    cron_enabled: bool = False
    cron_schedule: str = "0 9 * * 1-5"
    price_tolerance_pct: float = 0.5
    watchlist: list[str] = Field(default_factory=list, max_length=_MAX_WATCHLIST_ITEMS)
    output_language: str = "English"
    llm_provider: str = "openai"
    llm_model: str = "gpt-5.6-luna"
    fallback_llm_chain: list[FallbackLLMConfig] = Field(
        default_factory=list,
        max_length=MAX_FALLBACK_LLM_CHAIN_LENGTH,
    )
    investor_persona: str = "conservative"
    analyst_concurrency_limit: int = 1
    max_recur_limit: int = 1000
    benchmark_ticker: str | None = None
    max_debate_rounds: int = 1
    max_position_size_pct: float = 10.0
    max_risk_per_trade_pct: float = 2.0
    auto_execute_signals: bool = False
    allow_short_selling: bool = False
    max_concentration_pct: float = 25.0
    max_gross_exposure: float = 3.0
    strict_stop_loss_mode: bool = False
    correlation_risk_enabled: bool = False
    quality_gate_enabled: bool = False
    drawdown_breaker_enabled: bool = False
    max_portfolio_drawdown_pct: float = 20.0
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int = 2
    node_retry_base_delay: float = 1.0
    node_timeout_seconds: int = 120
    tool_timeout_seconds: int = 60
    circuit_breaker_threshold: int = 3
    circuit_breaker_cooldown: int = 60
    stall_timeout_seconds: int = 120
    max_active_alerts: int = 30
    max_ai_alerts_per_run: int = 3
    ai_alert_cooldown_hours: int = 24
    webhook_url: str | None = None
    webhook_enabled: bool = False
    webhook_events: list[str] = Field(default_factory=lambda: ["analysis_complete"], max_length=len(WEBHOOK_EVENTS))
    active_preset_name: str | None = None
    memory_embedder: str = "openai"
    memory_openai_embed_model: str = "text-embedding-3-small"
    memory_ollama_embed_model: str = "nomic-embed-text"
    agent_qa_enabled: bool = True
    anthropic_prompt_caching: bool = True
    max_report_chars_in_prompts: int = 6000
    max_debate_history_chars: int = 8000
    max_tool_output_chars: int = 12000
    analyst_prefilter_enabled: bool = False
    analyst_prefilter_min_samples: int = 5
    analyst_prefilter_max_win_rate: float = 40.0
    strategy_learning_enabled: bool = True
    decision_stability_mode: str = "shadow"
    decision_stability_min_quality: int = 70
    decision_stability_min_confidence: float = 0.65
    decision_stability_min_evidence_groups: int = 2
    reversal_verifier_enabled: bool = True
    confidence_calibration_enabled: bool = False
    regime_aware_weighting_enabled: bool = False
    memory_recall_count: int = 5
    summary_only_mode: bool = False
    news_article_limit: int = 20
    global_news_article_limit: int = 10
    global_news_lookback_days: int = 7

    @field_validator("watchlist")
    @classmethod
    def validate_watchlist(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_watchlist(value)

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url_shape(v)

    @field_validator("webhook_events")
    @classmethod
    def validate_webhook_events(cls, value: list[str]) -> list[str]:
        return _normalize_webhook_events(value)

    @field_validator("memory_embedder")
    @classmethod
    def validate_memory_embedder(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"openai", "ollama"}:
            raise ValueError("memory_embedder must be openai or ollama")
        return normalized


class SettingsRead(SettingsBase, ApiResponse):
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MemoryStatusResponse(BaseModel):
    enabled: bool
    store: str
    embedder: str | None
    embed_model: str | None
    needs_openai_key: bool
    agent_qa_enabled: bool


class LLMModelOption(BaseModel):
    value: str
    label: str
    supported_output_languages: list[str] | None = None


class LLMProviderCatalogEntry(BaseModel):
    label: str
    models: list[LLMModelOption]


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cron_enabled: bool | None = None
    cron_schedule: str | None = None
    price_tolerance_pct: float | None = Field(default=None, ge=0, le=50)
    watchlist: list[str] | None = Field(default=None, max_length=_MAX_WATCHLIST_ITEMS)
    output_language: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    fallback_llm_chain: list[FallbackLLMConfig] | None = Field(
        default=None,
        max_length=MAX_FALLBACK_LLM_CHAIN_LENGTH,
    )
    investor_persona: str | None = None
    analyst_concurrency_limit: int | None = Field(default=None, ge=1, le=16)
    max_recur_limit: int | None = Field(default=None, ge=100, le=5000)
    benchmark_ticker: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1, le=10)
    max_position_size_pct: float | None = Field(default=None, ge=1, le=100)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=50)
    auto_execute_signals: bool | None = None
    allow_short_selling: bool | None = None
    max_concentration_pct: float | None = Field(default=None, ge=1, le=100)
    max_gross_exposure: float | None = Field(default=None, ge=1, le=10)
    strict_stop_loss_mode: bool | None = None
    correlation_risk_enabled: bool | None = None
    quality_gate_enabled: bool | None = None
    drawdown_breaker_enabled: bool | None = None
    max_portfolio_drawdown_pct: float | None = Field(default=None, ge=1, le=100)
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int | None = Field(default=None, ge=1, le=10)
    node_retry_base_delay: float | None = Field(default=None, ge=0.1, le=10.0)
    node_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    tool_timeout_seconds: int | None = Field(default=None, ge=15, le=300)
    circuit_breaker_threshold: int | None = Field(default=None, ge=1, le=20)
    circuit_breaker_cooldown: int | None = Field(default=None, ge=10, le=600)
    stall_timeout_seconds: int | None = Field(default=None, ge=30, le=600)
    max_active_alerts: int | None = Field(default=None, ge=1, le=500)
    max_ai_alerts_per_run: int | None = Field(default=None, ge=0, le=20)
    ai_alert_cooldown_hours: int | None = Field(default=None, ge=0, le=720)
    webhook_url: str | None = None
    webhook_enabled: bool | None = None
    webhook_events: list[str] | None = Field(default=None, max_length=len(WEBHOOK_EVENTS))
    memory_embedder: str | None = Field(default=None, pattern="^(openai|ollama)$")
    memory_openai_embed_model: str | None = None
    memory_ollama_embed_model: str | None = None
    agent_qa_enabled: bool | None = None
    anthropic_prompt_caching: bool | None = None
    max_report_chars_in_prompts: int | None = Field(default=None, ge=500, le=50000)
    max_debate_history_chars: int | None = Field(default=None, ge=1000, le=100000)
    max_tool_output_chars: int | None = Field(default=None, ge=1000, le=100000)
    analyst_prefilter_enabled: bool | None = None
    analyst_prefilter_min_samples: int | None = Field(default=None, ge=1, le=100)
    analyst_prefilter_max_win_rate: float | None = Field(default=None, ge=0, le=100)
    strategy_learning_enabled: bool | None = None
    decision_stability_mode: str | None = Field(default=None, pattern="^(off|shadow|enforce)$")
    decision_stability_min_quality: int | None = Field(default=None, ge=0, le=100)
    decision_stability_min_confidence: float | None = Field(default=None, ge=0, le=1)
    decision_stability_min_evidence_groups: int | None = Field(default=None, ge=1, le=10)
    reversal_verifier_enabled: bool | None = None
    confidence_calibration_enabled: bool | None = None
    regime_aware_weighting_enabled: bool | None = None
    memory_recall_count: int | None = Field(default=None, ge=1, le=50)
    summary_only_mode: bool | None = None
    news_article_limit: int | None = Field(default=None, ge=1, le=100)
    global_news_article_limit: int | None = Field(default=None, ge=1, le=100)
    global_news_lookback_days: int | None = Field(default=None, ge=1, le=90)

    @field_validator("watchlist")
    @classmethod
    def validate_watchlist(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_watchlist(value)

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url_shape(v)

    @field_validator("webhook_events")
    @classmethod
    def validate_webhook_events(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_webhook_events(value) if value is not None else None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self) -> "SettingsUpdate":
        """Keep PATCH omission separate from an explicit database null.

        Every field is optional in this DTO so callers can send a partial
        update.  That does not make every persisted column nullable: accepting
        ``null`` for a boolean/number/string used to defer a confusing
        integrity error until the service flushed the ORM object.  Only the
        columns that are genuinely nullable may be cleared explicitly.
        """
        nullable_fields = {
            "anthropic_effort",
            "benchmark_ticker",
            "google_thinking_level",
            "openai_reasoning_effort",
            "webhook_url",
        }
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in nullable_fields:
                raise ValueError(f"{field} may not be null when provided")
        return self
