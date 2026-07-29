from typing import Any

from pydantic import BaseModel


class ShareCreateResponse(BaseModel):
    token: str
    expires_at: str


class SharedReportResponse(BaseModel):
    ticker: str
    trade_date: str | None = None
    signal: str | None = None
    market_report: str | None = None
    sentiment_report: str | None = None
    news_report: str | None = None
    fundamentals_report: str | None = None
    macro_report: str | None = None
    options_report: str | None = None
    quant_report: str | None = None
    earnings_report: str | None = None
    insider_report: str | None = None
    ownership_report: str | None = None
    ratings_report: str | None = None
    short_interest_report: str | None = None
    valuation_report: str | None = None
    catalyst_report: str | None = None
    review_report: str | None = None
    synthesis_report: str | None = None
    audit_report: str | None = None
    agent_qa_report: str | None = None
    investment_plan: str | None = None
    trader_plan: str | None = None
    final_decision: str | None = None
    bull_history: Any = None
    bear_history: Any = None
    investment_debate_history: Any = None
    risk_debate_history: Any = None
    judge_decision: str | None = None
    trader_proposal_json: str | None = None
    chart_annotations: Any = None
    risk_metrics: Any = None
    quality: Any = None
    degraded: bool = False
    failed_agents: list[str] = []
    duration_seconds: float | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    expires_at: str
    created_at: str
