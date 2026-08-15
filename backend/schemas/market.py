from typing import Literal

from pydantic import BaseModel


class OhlcvCandle(BaseModel):
    """One trading day plus the indicators the chart overlays on it.

    Every indicator is nullable: the leading rows of a series have no rolling
    window behind them yet, and `_compute_candles` emits ``None`` there rather
    than dropping the candle.
    """

    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int
    sma: float | None
    ema: float | None
    rsi: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_hist: float | None

class OhlcvResponse(BaseModel):
    ticker: str
    start_date: str
    end_date: str
    candles: list[OhlcvCandle]

class CustomIndicatorPoint(BaseModel):
    time: str
    #: ``None`` where the formula produced a non-finite result.
    value: float | None

class CustomIndicatorResponse(BaseModel):
    ticker: str
    formula: str
    series: list[CustomIndicatorPoint]

class FormulaAssistResponse(BaseModel):
    formula: str

class PatternKeyPoint(BaseModel):
    """A point the chart annotates, e.g. the neckline of a double top."""

    date: str
    price: float
    label: str

class DetectedPattern(BaseModel):
    #: Kept as a plain string rather than an enum: `pattern_detection_service`
    #: is where new pattern kinds are added, and a closed set here would turn
    #: adding one into a schema change.
    type: str
    label: str
    direction: Literal["bullish", "bearish"]
    start_date: str
    end_date: str
    key_points: list[PatternKeyPoint]
    confidence: float

class PatternsResponse(BaseModel):
    ticker: str
    period: str
    patterns: list[DetectedPattern]

class SentimentHistoryPoint(BaseModel):
    time: str
    value: float

class SentimentHistoryResponse(BaseModel):
    ticker: str
    history: list[SentimentHistoryPoint]
