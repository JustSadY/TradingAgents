from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base

# All navigable page keys in the application
ALL_PAGE_KEYS = [
    "dashboard", "analysis", "chart", "trading", "portfolio",
    "watchlist", "orders", "performance", "alerts",
    "ab-testing", "logs",
]
# Pages always accessible regardless of permissions (settings = API key management)
ALWAYS_ALLOWED = {"settings"}

ALL_SETTING_KEYS = ["general", "llm", "risk", "webhooks", "presets"]

# Maps settings sections to fields they control for backend validation
SECTION_FIELDS = {
    "general": [
        "trading_mode",
        "active_broker",
        "active_data_vendor",
        "output_language",
        "investor_persona",
        "benchmark_ticker",
    ],
    "llm": [
        "llm_provider",
        "llm_model",
        "backend_url",
        "openai_reasoning_effort",
        "anthropic_effort",
        "google_thinking_level",
        "selected_analysts",
        "analyst_models",
    ],
    "risk": [
        "max_risk_per_trade_pct",
        "max_position_size_pct",
        "max_debate_rounds",
        "max_risk_rounds",
        "analyst_concurrency_limit",
    ],
    "webhooks": [
        "webhook_url",
        "webhook_enabled",
        "webhook_events",
    ],
}


class UserPagePermission(Base):
    """Per-user, per-page access control. Admin bypasses all checks."""
    __tablename__ = "user_page_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    page_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "page_key", name="uq_user_page"),)


class UserSettingPermission(Base):
    """Per-user settings section access control. Admin bypasses all checks."""
    __tablename__ = "user_setting_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "setting_key", name="uq_user_setting"),)

