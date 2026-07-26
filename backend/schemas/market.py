from pydantic import BaseModel


class FormulaAssistResponse(BaseModel):
    formula: str


class PatternsResponse(BaseModel):
    ticker: str
    period: str
    patterns: list[dict]


class SentimentHistoryPoint(BaseModel):
    time: str
    value: float


class SentimentHistoryResponse(BaseModel):
    ticker: str
    history: list[SentimentHistoryPoint]
