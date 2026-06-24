from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.constants import PAGE_KEYS, SETTING_KEYS
from backend.core.database import Base

ALL_PAGE_KEYS = [k for k in PAGE_KEYS if k != "settings"]
ALWAYS_ALLOWED = {"settings"}
ALL_SETTING_KEYS = SETTING_KEYS
SECTION_FIELDS = {
    "general": [
        "output_language",
        "investor_persona",
        "benchmark_ticker",
    ],
    "llm": [
        "llm_provider",
        "llm_model",
        "fallback_llm_provider",
        "fallback_llm_model",
        "openai_reasoning_effort",
        "anthropic_effort",
        "google_thinking_level",
    ],
    "risk": [
        "max_risk_per_trade_pct",
        "max_position_size_pct",
        "max_debate_rounds",
        "max_risk_rounds",
        "analyst_concurrency_limit",
        "node_retry_attempts",
        "node_retry_base_delay",
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
}


class UserPagePermission(Base):
    __tablename__ = "user_page_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    page_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "page_key", name="uq_user_page"),)


class UserSettingPermission(Base):
    __tablename__ = "user_setting_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "setting_key", name="uq_user_setting"),)
