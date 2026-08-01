from pydantic import BaseModel

class ScreenResultItem(BaseModel):
    ticker: str
    score: float
    momentum_1m_pct: float
    trend: str
    volume_surge: float
    rsi_14: float
    signals: list[str] = []

class ScreenResponse(BaseModel):
    results: list[ScreenResultItem]
