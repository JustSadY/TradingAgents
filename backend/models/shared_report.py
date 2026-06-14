from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class SharedReport(Base):
    __tablename__ = "shared_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    analysis_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_results.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, default=lambda: uuid.uuid4().hex
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC) + timedelta(hours=48)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
