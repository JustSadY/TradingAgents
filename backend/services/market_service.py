"""Market data + charting indicators for the dashboard chart endpoints.

OHLCV assembly, technical-indicator computation, custom-formula evaluation and
sentiment history used to be computed inline (and synchronously, blocking the
event loop) inside ``api/market.py``. They live here now, with ticker
validation applied consistently and the blocking yfinance/pandas work pushed to
a worker thread.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import PERIOD_DELTAS, SIGNAL_SENTIMENT_VALUES
from backend.core.utils import safe_ticker_component
from backend.services.indicator_service import calculate_ema, calculate_macd, calculate_rsi, evaluate_formula_safely
from backend.services.market_data_service import get_historical_data

_logger = logging.getLogger(__name__)


class MarketDataError(Exception):
    """Raised for client-correctable problems (bad ticker/date/no data)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _clean_ticker(ticker: str) -> str:
    ticker = (ticker or "").upper().strip()
    try:
        safe_ticker_component(ticker)
    except ValueError as exc:
        raise MarketDataError(str(exc), status_code=422) from exc
    return ticker


def _resolve_dates(period: str, start_date: str | None, end_date: str | None) -> tuple[str, str]:
    if start_date and end_date:
        s, e = start_date, end_date
    else:
        end = datetime.now()
        start = end - PERIOD_DELTAS.get(period, PERIOD_DELTAS["1y"])
        s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    try:
        datetime.strptime(s, "%Y-%m-%d")
        datetime.strptime(e, "%Y-%m-%d")
    except ValueError as exc:
        raise MarketDataError("Date format must be YYYY-MM-DD") from exc
    return s, e


def _compute_candles(data) -> list[dict]:
    import numpy as np

    # Ensure we have required columns and skip rows with missing OHLC data
    data = data.dropna(subset=["Open", "High", "Low", "Close"])

    if data.empty:
        return []

    data["sma"] = data["Close"].rolling(window=20).mean()
    data["ema"] = calculate_ema(data["Close"], span=20)
    data["rsi"] = calculate_rsi(data["Close"], period=14)
    macd_line, macd_signal = calculate_macd(data["Close"], fast=12, slow=26, signal=9)
    data["macd_line"] = macd_line
    data["macd_signal"] = macd_signal
    data["macd_hist"] = data["macd_line"] - data["macd_signal"]
    data = data.replace({np.nan: None})

    def _r(value):
        return round(float(value), 2) if value is not None else None

    candles = []
    for ts, row in data.iterrows():
        candles.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "open": _r(row["Open"]),
                "high": _r(row["High"]),
                "low": _r(row["Low"]),
                "close": _r(row["Close"]),
                "volume": int(row.get("Volume", 0) or 0),
                "sma": _r(row["sma"]),
                "ema": _r(row["ema"]),
                "rsi": _r(row["rsi"]),
                "macd_line": _r(row["macd_line"]),
                "macd_signal": _r(row["macd_signal"]),
                "macd_hist": _r(row["macd_hist"]),
            }
        )
    return candles


async def get_ohlcv(ticker: str, period: str, start_date: str | None, end_date: str | None) -> dict:
    ticker = _clean_ticker(ticker)
    s, e = _resolve_dates(period, start_date, end_date)

    data = await get_historical_data(ticker, s, e)
    if data.empty:
        raise MarketDataError(f"No data found for {ticker}", status_code=404)

    candles = _compute_candles(data)
    return {"ticker": ticker, "start_date": s, "end_date": e, "candles": candles}


async def get_custom_indicator_series(
    ticker: str,
    formula: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> dict:
    ticker = _clean_ticker(ticker)
    s, e = _resolve_dates(period, start_date, end_date)

    import numpy as np

    data = await get_historical_data(ticker, s, e)
    if data.empty:
        raise MarketDataError(f"No data found for {ticker}", status_code=404)

    series = evaluate_formula_safely(data, formula).replace({np.nan: None})
    results = [
        {"time": ts.strftime("%Y-%m-%d"), "value": round(float(val), 4) if val is not None else None}
        for ts, val in series.items()
    ]

    return {"ticker": ticker, "formula": formula, "series": results}


async def get_sentiment_history(db: AsyncSession, ticker: str, user=None) -> dict:
    ticker = _clean_ticker(ticker)
    from backend.repositories.analysis import get_sentiment_history_by_ticker

    rows = await get_sentiment_history_by_ticker(db, ticker, user=user)
    history = [{"time": trade_date, "value": SIGNAL_SENTIMENT_VALUES.get(signal, 0.0)} for trade_date, signal in rows]
    return {"ticker": ticker, "history": history}
