from datetime import datetime

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
    benchmark_ticker: str | None = None
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1
    max_position_size_pct: float = 10.0
    max_risk_per_trade_pct: float = 2.0
    strict_stop_loss_mode: bool = False
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int = 2
    node_retry_base_delay: float = 1.0
    webhook_url: str | None = None
    webhook_enabled: bool = False
    webhook_events: str = '["analysis_complete"]'
    active_preset_name: str | None = None
    # Per-user vector memory config (the Pinecone/OpenAI keys are stored
    # separately as encrypted API keys).
    pinecone_index: str = "tradingagents-memory"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    memory_embedder: str = "pinecone"
    pinecone_embed_model: str = "llama-text-embed-v2"
    memory_openai_embed_model: str = "text-embedding-3-small"
    agent_qa_enabled: bool = True
    # Token-budget controls.
    anthropic_prompt_caching: bool = True
    max_report_chars_in_prompts: int = 6000
    max_debate_history_chars: int = 8000
    max_tool_output_chars: int = 12000


class SettingsRead(SettingsBase):
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    # We explicitly define these to keep the validation logic (ge, le)
    cron_enabled: bool | None = None
    cron_schedule: str | None = None
    price_tolerance_pct: float | None = Field(default=None, ge=0, le=50)
    watchlist: list[str] | None = None
    output_language: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    investor_persona: str | None = None
    analyst_concurrency_limit: int | None = Field(default=None, ge=1, le=16)
    max_recur_limit: int | None = Field(default=None, ge=100, le=5000)
    benchmark_ticker: str | None = None
    max_debate_rounds: int | None = Field(default=None, ge=1, le=10)
    max_risk_rounds: int | None = Field(default=None, ge=1, le=10)
    max_position_size_pct: float | None = Field(default=None, ge=1, le=100)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.1, le=50)
    strict_stop_loss_mode: bool | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    google_thinking_level: str | None = None
    node_retry_attempts: int | None = Field(default=None, ge=1, le=10)
    node_retry_base_delay: float | None = Field(default=None, ge=0.1, le=10.0)
    webhook_url: str | None = None
    webhook_enabled: bool | None = None
    webhook_events: str | None = None
    active_preset_name: str | None = None
    pinecone_index: str | None = None
    pinecone_cloud: str | None = None
    pinecone_region: str | None = None
    memory_embedder: str | None = None
    pinecone_embed_model: str | None = None
    memory_openai_embed_model: str | None = None
    agent_qa_enabled: bool | None = None
    anthropic_prompt_caching: bool | None = None
    max_report_chars_in_prompts: int | None = Field(default=None, ge=500, le=50000)
    max_debate_history_chars: int | None = Field(default=None, ge=1000, le=100000)
    max_tool_output_chars: int | None = Field(default=None, ge=1000, le=100000)
