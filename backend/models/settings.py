import json
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (Index("uq_app_settings_owner", text("COALESCE(user_id, 0)"), unique=True),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    cron_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cron_schedule: Mapped[str] = mapped_column(String(100), default="0 9 * * 1-5")
    price_tolerance_pct: Mapped[float] = mapped_column(Float, default=0.5)
    _watchlist: Mapped[str] = mapped_column("watchlist", Text, default="[]")
    output_language: Mapped[str] = mapped_column(String(50), default="English")
    llm_provider: Mapped[str] = mapped_column(String(50), default="openai")
    llm_model: Mapped[str] = mapped_column(String(100), default="gpt-5.6-luna")
    fallback_llm_chain: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list, nullable=False)
    investor_persona: Mapped[str] = mapped_column(String(50), default="conservative")
    analyst_concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)
    max_recur_limit: Mapped[int] = mapped_column(Integer, default=1000)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    openai_reasoning_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    anthropic_effort: Mapped[str | None] = mapped_column(String(20), nullable=True)
    google_thinking_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    max_debate_rounds: Mapped[int] = mapped_column(Integer, default=1)
    max_position_size_pct: Mapped[float] = mapped_column(Float, default=10.0)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=2.0)
    auto_execute_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_short_selling: Mapped[bool] = mapped_column(Boolean, default=False)
    max_concentration_pct: Mapped[float] = mapped_column(Float, default=25.0)
    max_gross_exposure: Mapped[float] = mapped_column(Float, default=3.0)
    strict_stop_loss_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    correlation_risk_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_gate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    drawdown_breaker_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_portfolio_drawdown_pct: Mapped[float] = mapped_column(Float, default=20.0)
    node_retry_attempts: Mapped[int] = mapped_column(Integer, default=2)
    node_retry_base_delay: Mapped[float] = mapped_column(Float, default=1.0)
    node_timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    tool_timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    circuit_breaker_threshold: Mapped[int] = mapped_column(Integer, default=3)
    circuit_breaker_cooldown: Mapped[int] = mapped_column(Integer, default=60)
    stall_timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    max_active_alerts: Mapped[int] = mapped_column(Integer, default=30)
    max_ai_alerts_per_run: Mapped[int] = mapped_column(Integer, default=3)
    ai_alert_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    webhook_events: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["analysis_complete"], nullable=False)
    active_preset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Mem0 is the only runtime long-term-memory backend.  The Pinecone columns
    # remain temporarily for backwards-compatible settings rows/API payloads;
    # memory_service no longer reads them.
    memory_store: Mapped[str] = mapped_column(String(20), default="pgvector")
    pinecone_index: Mapped[str] = mapped_column(String(100), default="tradingagents-memory")
    pinecone_cloud: Mapped[str] = mapped_column(String(20), default="aws")
    pinecone_region: Mapped[str] = mapped_column(String(30), default="us-east-1")
    memory_embedder: Mapped[str] = mapped_column(String(20), default="openai")
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
    # Strategy continuity / decision-stability controls.  Shadow is the safe
    # default: the controller records what it would have changed without
    # changing the Portfolio Manager's executable decision.
    strategy_learning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    decision_stability_mode: Mapped[str] = mapped_column(String(20), default="shadow")
    decision_stability_min_quality: Mapped[int] = mapped_column(Integer, default=70)
    decision_stability_min_confidence: Mapped[float] = mapped_column(Float, default=0.65)
    decision_stability_min_evidence_groups: Mapped[int] = mapped_column(Integer, default=2)
    reversal_verifier_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence_calibration_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    regime_aware_weighting_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_recall_count: Mapped[int] = mapped_column(Integer, default=5)
    summary_only_mode: Mapped[bool] = mapped_column(Boolean, default=False)
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
