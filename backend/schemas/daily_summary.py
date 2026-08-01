from pydantic import BaseModel

class DailySummaryResponse(BaseModel):
    id: int | None = None
    date: str | None = None
    summary: str | None = None
    tickers: list[str] = []
    generated_at: str | None = None
