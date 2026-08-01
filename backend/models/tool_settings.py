from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base

_USERS_ID_FK = "users.id"

class AgentToolSetting(Base):
    __tablename__ = "agent_tool_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(20), default="user", nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey(_USERS_ID_FK, ondelete="CASCADE"), nullable=True, index=True
    )
    tool_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    settings: Mapped[dict] = mapped_column("settings_json", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("scope", "user_id", "tool_key", name="uq_agent_tool_settings_scope_user_tool"),)

class UserAgentAccess(Base):
    __tablename__ = "user_agent_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(_USERS_ID_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    agent_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    can_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("user_id", "agent_key", name="uq_user_agent_access_user_agent"),)

class UserToolAccess(Base):
    __tablename__ = "user_tool_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(_USERS_ID_FK, ondelete="CASCADE"), nullable=False, index=True
    )
    tool_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_use: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_enable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("user_id", "tool_key", name="uq_user_tool_access_user_tool"),)

class UserToolFieldAccess(Base):
    __tablename__ = "user_tool_field_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(_USERS_ID_FK, ondelete="CASCADE"), nullable=False, index=True
    )

    tool_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "tool_key", "field_key", name="uq_user_tool_field_access_user_tool_field"),
    )
