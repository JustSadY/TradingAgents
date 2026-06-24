from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
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
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    articles_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class AnalystReportCache(Base):
    __tablename__ = "analyst_report_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analyst_key: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    analysis_result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
