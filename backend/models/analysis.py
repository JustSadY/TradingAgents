from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base
class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="stock")
    signal: Mapped[str | None] = mapped_column(String(50), nullable=True)
    market_report: Mapped[str] = mapped_column(Text, default="")
    sentiment_report: Mapped[str] = mapped_column(Text, default="")
    news_report: Mapped[str] = mapped_column(Text, default="")
    fundamentals_report: Mapped[str] = mapped_column(Text, default="")
    macro_report: Mapped[str] = mapped_column(Text, default="")
    options_report: Mapped[str] = mapped_column(Text, default="")
    quant_report: Mapped[str] = mapped_column(Text, default="")
    earnings_report: Mapped[str] = mapped_column(Text, default="")
    review_report: Mapped[str] = mapped_column(Text, default="")
    investment_plan: Mapped[str] = mapped_column(Text, default="")
    trader_plan: Mapped[str] = mapped_column(Text, default="")
    final_decision: Mapped[str] = mapped_column(Text, default="")
    reflection: Mapped[str] = mapped_column(Text, default="")
    bull_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    bear_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    investment_debate_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    risk_debate_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    judge_decision: Mapped[str] = mapped_column(Text, default="")
    chart_annotations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preset_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    raw_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    chats: Mapped[list["AnalysisChat"]] = relationship(
        "AnalysisChat", back_populates="analysis", cascade="all, delete-orphan"
    )
class AnalysisChat(Base):
    __tablename__ = "analysis_chats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    analysis: Mapped[AnalysisResult] = relationship("AnalysisResult", back_populates="chats")
