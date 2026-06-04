import json
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.core.database import Base


class AgentSetting(Base):
    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    agent_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    _settings_json: Mapped[str] = mapped_column("settings_json", Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("scope", "user_id", "agent_key", name="uq_agent_settings_scope_user_agent"),
    )

    @property
    def settings(self) -> dict:
        return json.loads(self._settings_json or "{}")

    @settings.setter
    def settings(self, value: dict):
        self._settings_json = json.dumps(value)
