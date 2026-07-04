from pydantic import BaseModel


class FormulaAssistResponse(BaseModel):
    formula: str


class PatternsResponse(BaseModel):
    ticker: str
    period: str
    patterns: list[dict]
