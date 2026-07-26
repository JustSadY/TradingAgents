from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class NewsCache(Base):
    __tablename__ = "news_cache"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    news_json: Mapped[list] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class NewsAnalysisCache(Base):
    __tablename__ = "news_analysis_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable for system-triggered runs with no owning user; lookups treat
    # NULL as its own bucket so those runs never share cache with real users.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    articles_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Fingerprint of provider/model/persona/language — lets the stale-data
    # fallback below match "same config" without re-deriving it from the full
    # data hash (which also encodes the fetched articles).
    config_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class AnalystReportCache(Base):
    __tablename__ = "analyst_report_cache"
    __table_args__ = (
        Index("ix_analyst_report_cache_lookup", "user_id", "analyst_key", "ticker", "data_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Nullable for system-triggered runs with no owning user; lookups treat
    # NULL as its own bucket so those runs never share cache with real users.
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    analyst_key: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Fingerprint of provider/model/persona/language — lets the stale-data
    # fallback below match "same config" without re-deriving it from the full
    # data hash (which also encodes the fetched data blocks).
    config_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
