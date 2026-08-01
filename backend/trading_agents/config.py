import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HOME = Path.home() / ".tradingagents"
MAX_FALLBACK_LLM_CHAIN_LENGTH = 3

class FallbackLLMConfig(BaseModel):
    """One ordered provider/model failover target for an analysis run."""

    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("provider")
    @classmethod
    def normalise_provider(cls, value: str) -> str:
        normalised = value.strip()
        if not normalised:
            raise ValueError("fallback provider must not be empty")
        return normalised.lower()

    @field_validator("model")
    @classmethod
    def normalise_model(cls, value: str) -> str:
        normalised = value.strip()
        if not normalised:
            raise ValueError("fallback model must not be empty")
        return normalised

def normalize_fallback_llm_chain(value: Any) -> list[dict[str, str]]:
    """Validate and canonicalize the ordered LLM failover contract.

    Runtime callers pass plain dictionaries while :class:`TradingAgentsConfig`
    uses typed entries.  Keeping the conversion here gives both paths one
    strict representation and prevents stale single-provider settings from
    being interpreted by the graph.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("fallback_llm_chain must be a list of provider/model entries")
    if len(value) > MAX_FALLBACK_LLM_CHAIN_LENGTH:
        raise ValueError(f"fallback_llm_chain cannot contain more than {MAX_FALLBACK_LLM_CHAIN_LENGTH} entries")
    return [
        FallbackLLMConfig.model_validate(entry.model_dump() if isinstance(entry, BaseModel) else entry).model_dump()
        for entry in value
    ]

class TradingAgentsConfig(BaseModel):
    project_dir: str = Field(
        default_factory=lambda: str(Path(__file__).parent.resolve()),
    )
    results_dir: str = Field(
        default_factory=lambda: os.environ.get("TRADINGAGENTS_RESULTS_DIR", str(_HOME / "logs")),
    )
    data_cache_dir: str = Field(
        default_factory=lambda: os.environ.get(
            "TRADINGAGENTS_CACHE_DIR", os.environ.get("TRADINGAGENTS_DATA_CACHE_DIR", str(_HOME / "cache"))
        ),
    )
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    fallback_llm_chain: list[FallbackLLMConfig] = Field(
        default_factory=list,
        max_length=MAX_FALLBACK_LLM_CHAIN_LENGTH,
    )
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    output_language: str = "English"
    investor_persona: str = "conservative"
    max_debate_rounds: int = Field(default=1, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=10)
    max_recur_limit: int = Field(default=1000, ge=1)
    keep_checkpoints: bool = True
    analyst_concurrency_limit: int = Field(default=1, ge=1)
    node_retry_attempts: int = Field(default=2, ge=1)
    node_retry_base_delay: float = Field(default=1.0, ge=0.0)
    node_timeout_seconds: int = Field(default=120, ge=30)
    tool_timeout_seconds: int = Field(default=60, ge=15)
    circuit_breaker_threshold: int = Field(default=3, ge=1)
    circuit_breaker_cooldown: int = Field(default=60, ge=10)
    max_analyst_tool_turns: int = Field(default=10, ge=2)
    stall_timeout_seconds: int = Field(default=120, ge=30)
    alpha_vantage_rate_limit_calls: int = Field(default=5, ge=1)
    alpha_vantage_rate_limit_window: float = Field(default=60.0, ge=1.0)
    alpha_vantage_retry_attempts: int = Field(default=3, ge=0)
    alpha_vantage_retry_delay: float = Field(default=2.0, ge=0.0)
    api_cache_max_entries: int = Field(default=5000, ge=100)
    memory_recall_count: int = Field(default=5, ge=1)
    summary_only_mode: bool = False
    max_report_chars_in_prompts: int = Field(default=6000, ge=500)
    max_debate_history_chars: int = Field(default=8000, ge=1000)
    max_tool_output_chars: int = Field(default=12000, ge=1000)
    anthropic_prompt_caching: bool = True
    news_article_limit: int = Field(default=20, ge=1)
    global_news_article_limit: int = Field(default=10, ge=1)
    global_news_lookback_days: int = Field(default=7, ge=1)
    global_news_queries: list[str] = Field(
        default_factory=lambda: [
            "Federal Reserve interest rates inflation",
            "S&P 500 earnings GDP economic outlook",
            "geopolitical risk trade war sanctions",
            "ECB Bank of England BOJ central bank policy",
            "oil commodities supply chain energy",
        ]
    )
    data_vendors: dict[str, str] = Field(
        default_factory=lambda: {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        }
    )
    tool_vendors: dict[str, str] = Field(default_factory=dict)
    benchmark_ticker: str | None = None
    benchmark_map: dict[str, str] = Field(
        default_factory=lambda: {
            ".NS": "^NSEI",
            ".BO": "^BSESN",
            ".T": "^N225",
            ".HK": "^HSI",
            ".L": "^FTSE",
            ".TO": "^GSPTSE",
            ".AX": "^AXJO",
            "": "SPY",
        }
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalise_provider(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("fallback_llm_chain", mode="before")
    @classmethod
    def normalise_fallback_chain(cls, value: Any) -> list[dict[str, str]]:
        return normalize_fallback_llm_chain(value)

    @field_validator("anthropic_effort", "openai_reasoning_effort", mode="before")
    @classmethod
    def normalise_effort(cls, v):
        if v is None:
            return v
        return v.strip().lower()

    def to_dict(self) -> dict:
        return self.model_dump()
