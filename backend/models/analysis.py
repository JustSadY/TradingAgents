from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        Index("ix_analysis_results_user_ticker", "user_id", "ticker"),
        Index("ix_analysis_results_trade_date", "trade_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
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
    insider_report: Mapped[str] = mapped_column(Text, default="")
    ownership_report: Mapped[str] = mapped_column(Text, default="")
    ratings_report: Mapped[str] = mapped_column(Text, default="")
    short_interest_report: Mapped[str] = mapped_column(Text, default="")
    valuation_report: Mapped[str] = mapped_column(Text, default="")
    catalyst_report: Mapped[str] = mapped_column(Text, default="")
    review_report: Mapped[str] = mapped_column(Text, default="")
    synthesis_report: Mapped[str] = mapped_column(Text, default="")
    audit_report: Mapped[str] = mapped_column(Text, default="")
    agent_qa_report: Mapped[str] = mapped_column(Text, default="")
    investment_plan: Mapped[str] = mapped_column(Text, default="")
    # The pre-analysis investigation brief and structured evidence are kept
    # independently from the human-readable reports.  They are machine-facing
    # inputs to the strategy/controller and must never be reconstructed by
    # parsing Markdown on a later run.
    analysis_plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    synthesis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    market_regime_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_candidate_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # PM proposal and controller-accepted decision intentionally have separate
    # durable columns.  The executor is allowed to consume only the latter.
    pm_proposal_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    portfolio_decision_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision_transition_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    calibrated_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_update_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    strategy_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("asset_strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    strategy_before_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_after_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Historical/time-travel/shadow runs are auditable analysis artifacts, not
    # live learning observations.  This prevents simulated outcomes from
    # quietly entering calibration, analyst-weight, episodic-memory or active
    # strategy learning.
    analysis_mode: Mapped[str] = mapped_column(String(20), default="live", index=True)
    learning_eligible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    final_decision: Mapped[str] = mapped_column(Text, default="")
    reflection: Mapped[str] = mapped_column(Text, default="")
    bull_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    bear_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    investment_debate_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    risk_debate_history: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    judge_decision: Mapped[str] = mapped_column(Text, default="")
    chart_annotations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    degraded: Mapped[bool] = mapped_column(Integer, default=0)
    failed_agents: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    raw_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    holding_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    analysis: Mapped[AnalysisResult] = relationship("AnalysisResult", back_populates="chats")
