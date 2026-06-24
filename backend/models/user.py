from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False, server_default="user")
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_keys_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bumped on logout / password change to invalidate all previously issued
    # access & refresh tokens (they carry the version they were minted with).
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "owner")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"
