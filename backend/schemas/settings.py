from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.constants import WEBHOOK_EVENTS
from backend.trading_agents.config import MAX_FALLBACK_LLM_CHAIN_LENGTH, FallbackLLMConfig

def _validate_webhook_url_shape(v: str | None) -> str | None:
    """Shared shape check for the ``webhook_url`` field on both settings models.

    This only validates it's a well-formed http(s) URL — it can't do the DNS
    resolution needed to catch SSRF targets (localhost, 169.254.169.254,
    RFC1918 ranges). That check runs separately at the actual save path via
    ``notification_service.validate_webhook_url``.
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
    watchlist: list[str] = []
    output_language: str = "English"
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    fallback_llm_chain: list[FallbackLLMConfig] = Field(
        default_factory=list,
        max_length=MAX_FALLBACK_LLM_CHAIN_LENGTH,
    )
    investor_persona: str = "conservative"
    analyst_concurrency_limit: int = 1
    max_recur_limit: int = 1000
    benchmark_ticker: str | None = None
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
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
    memory_store: str = "pinecone"
    pinecone_index: str = "tradingagents-memory"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    memory_embedder: str = "pinecone"
    pinecone_embed_model: str = "llama-text-embed-v2"
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
    memory_recall_count: int = 5
    summary_only_mode: bool = False
    news_article_limit: int = 20
    global_news_article_limit: int = 10
    global_news_lookback_days: int = 7

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url_shape(v)

    @field_validator("webhook_events")
    @classmethod
    def validate_webhook_events(cls, value: list[str]) -> list[str]:
        return _normalize_webhook_events(value)

class SettingsRead(SettingsBase):
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class MemoryStatusResponse(BaseModel):
    enabled: bool
    store: str
    embedder: str | None
    index: str | None
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
    watchlist: list[str] | None = None
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
    max_risk_rounds: int | None = Field(default=None, ge=1, le=10)
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
    memory_store: str | None = None
    pinecone_index: str | None = None
    pinecone_cloud: str | None = None
    pinecone_region: str | None = None
    memory_embedder: str | None = None
    pinecone_embed_model: str | None = None
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
    memory_recall_count: int | None = Field(default=None, ge=1, le=50)
    summary_only_mode: bool | None = None
    news_article_limit: int | None = Field(default=None, ge=1, le=100)
    global_news_article_limit: int | None = Field(default=None, ge=1, le=100)
    global_news_lookback_days: int | None = Field(default=None, ge=1, le=90)

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
