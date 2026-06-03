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


class UserPagePermission(Base):
    """Per-user, per-page access control. Admin bypasses all checks."""
    __tablename__ = "user_page_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    page_key: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "page_key", name="uq_user_page"),)
