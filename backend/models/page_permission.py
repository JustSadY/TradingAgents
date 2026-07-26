from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.constants import PAGE_KEYS, SETTING_KEYS
from backend.core.database import Base

ALL_PAGE_KEYS = [k for k in PAGE_KEYS if k != "settings"]
ALWAYS_ALLOWED = {"settings"}
ALL_SETTING_KEYS = SETTING_KEYS
SECTION_FIELDS = {
    "general": [
        "watchlist",
        "output_language",
        "investor_persona",
        "benchmark_ticker",
        "price_tolerance_pct",
        "summary_only_mode",
        "news_article_limit",
        "global_news_article_limit",
        "global_news_lookback_days",
    ],
    "llm": [
        "llm_provider",
        "llm_model",
        "fallback_llm_provider",
        "fallback_llm_model",
        "openai_reasoning_effort",
        "anthropic_effort",
        "google_thinking_level",
        "anthropic_prompt_caching",
    ],
    "risk": [
        "max_risk_per_trade_pct",
        "max_position_size_pct",
        "max_debate_rounds",
        "max_risk_rounds",
        "analyst_concurrency_limit",
        "strict_stop_loss_mode",
        "correlation_risk_enabled",
        "quality_gate_enabled",
        "drawdown_breaker_enabled",
        "max_portfolio_drawdown_pct",
        "node_retry_attempts",
        "node_retry_base_delay",
        "node_timeout_seconds",
        "tool_timeout_seconds",
        "circuit_breaker_threshold",
        "circuit_breaker_cooldown",
        "stall_timeout_seconds",
        "max_report_chars_in_prompts",
        "max_debate_history_chars",
        "max_tool_output_chars",
        "analyst_prefilter_enabled",
        "analyst_prefilter_min_samples",
        "analyst_prefilter_max_win_rate",
        # Kept here until the dedicated risk settings schema is loaded; this
        # makes permission checks deny-by-default during rolling upgrades.
        "allow_short_selling",
        "max_concentration_pct",
        "max_gross_exposure",
    ],
    "webhooks": [
        "webhook_url",
        "webhook_enabled",
        "webhook_events",
    ],
    "cron": [
        "cron_enabled",
        "cron_schedule",
    ],
    "memory": [
        "memory_store",
        "pinecone_index",
        "pinecone_cloud",
        "pinecone_region",
        "memory_embedder",
        "pinecone_embed_model",
        "memory_openai_embed_model",
        "memory_ollama_embed_model",
        "agent_qa_enabled",
        "memory_recall_count",
    ],
    "presets": ["active_preset_name"],
    # Agent and tool settings live in their own endpoints and schemas.  They
    # intentionally have no AppSettings field mapping.
}


class UserPagePermission(Base):
    __tablename__ = "user_page_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    page_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "page_key", name="uq_user_page"),)


class UserSettingPermission(Base):
    __tablename__ = "user_setting_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "setting_key", name="uq_user_setting"),)
