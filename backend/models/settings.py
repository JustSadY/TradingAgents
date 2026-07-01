import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=0.5)
    _watchlist: Mapped[str] = mapped_column("watchlist", Text, default="[]")
    output_language: Mapped[str] = mapped_column(String(50), default="English")
    llm_provider: Mapped[str] = mapped_column(String(50), default="openai")
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    fallback_llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fallback_llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    correlation_risk_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_gate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    drawdown_breaker_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_portfolio_drawdown_pct: Mapped[float] = mapped_column(Float, default=20.0)
    node_retry_attempts: Mapped[int] = mapped_column(Integer, default=2)
    node_retry_base_delay: Mapped[float] = mapped_column(Float, default=1.0)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_events: Mapped[str] = mapped_column(Text, default='["analysis_complete"]')
    active_preset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    memory_store: Mapped[str] = mapped_column(String(20), default="pinecone")
    pinecone_index: Mapped[str] = mapped_column(String(100), default="tradingagents-memory")
    pinecone_cloud: Mapped[str] = mapped_column(String(20), default="aws")
    pinecone_region: Mapped[str] = mapped_column(String(30), default="us-east-1")
    memory_embedder: Mapped[str] = mapped_column(String(20), default="pinecone")
    pinecone_embed_model: Mapped[str] = mapped_column(String(60), default="llama-text-embed-v2")
    memory_openai_embed_model: Mapped[str] = mapped_column(String(60), default="text-embedding-3-small")
    memory_ollama_embed_model: Mapped[str] = mapped_column(String(60), default="nomic-embed-text")
    agent_qa_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anthropic_prompt_caching: Mapped[bool] = mapped_column(Boolean, default=True)
    max_report_chars_in_prompts: Mapped[int] = mapped_column(Integer, default=6000)
    max_debate_history_chars: Mapped[int] = mapped_column(Integer, default=8000)
    max_tool_output_chars: Mapped[int] = mapped_column(Integer, default=12000)
    analyst_prefilter_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    analyst_prefilter_min_samples: Mapped[int] = mapped_column(Integer, default=5)
    analyst_prefilter_max_win_rate: Mapped[float] = mapped_column(Float, default=40.0)
    memory_recall_count: Mapped[int] = mapped_column(Integer, default=5)
    news_article_limit: Mapped[int] = mapped_column(Integer, default=20)
    global_news_article_limit: Mapped[int] = mapped_column(Integer, default=10)
    global_news_lookback_days: Mapped[int] = mapped_column(Integer, default=7)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def watchlist(self) -> list[str]:
        return json.loads(self._watchlist or "[]")

    @watchlist.setter
    def watchlist(self, value: list[str]):
        self._watchlist = json.dumps(value)
