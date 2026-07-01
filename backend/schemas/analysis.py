from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AnalysisRunRequest(BaseModel):
    ticker: str
    trade_date: str
    asset_type: str = "stock"


class AnalysisRunResponse(BaseModel):
    task_id: str
    ticker: str
    trade_date: str
    message: str = "Analysis started"


class AnalysisResultRead(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    macro_report: str
    options_report: str
    quant_report: str
    earnings_report: str
    insider_report: str = ""
    ownership_report: str = ""
    ratings_report: str = ""
    short_interest_report: str = ""
    valuation_report: str = ""
    catalyst_report: str = ""
    review_report: str
    agent_qa_report: str = ""
    investment_plan: str
    trader_plan: str
    final_decision: str
    bull_history: Any = None
    bear_history: Any = None
    investment_debate_history: Any = None
    risk_debate_history: Any = None
    judge_decision: str = ""
    chart_annotations: Any = None
    quality: Any = None
    llm_calls: int
    tool_calls: int
    tokens_in: int
    tokens_out: int
    estimated_cost_usd: float = 0.0
    llm_provider: str | None = None
    llm_model: str | None = None
    preset_name: str | None = None
    duration_seconds: float
    triggered_by: str
    created_at: datetime
    raw_return: float | None = None
    alpha_return: float | None = None
    holding_days: int | None = None

    model_config = ConfigDict(from_attributes=True)


class AnalysisListItem(BaseModel):
    id: int
    ticker: str
    trade_date: str
    asset_type: str
    signal: str | None
    duration_seconds: float
    triggered_by: str
    created_at: datetime
    chart_annotations: Any = None
    llm_provider: str | None = None
    llm_model: str | None = None
    preset_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    message: str
