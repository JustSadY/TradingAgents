"""Market data + charting indicators for the dashboard chart endpoints.

OHLCV assembly, technical-indicator computation, custom-formula evaluation and
sentiment history used to be computed inline (and synchronously, blocking the
event loop) inside ``api/market.py``. They live here now, with ticker
validation applied consistently and the blocking yfinance/pandas work pushed to
a worker thread.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.utils import safe_ticker_component
from backend.models.analysis import AnalysisResult

_logger = logging.getLogger(__name__)

_PERIOD_DELTAS = {
    "1m": timedelta(days=31),
    "3m": timedelta(days=92),
    "6m": timedelta(days=183),
    "1y": timedelta(days=365),
    "2y": timedelta(days=730),
    "5y": timedelta(days=1825),
}

_SIGNAL_SENTIMENT = {
    "Buy": 0.85, "Overweight": 0.45, "Hold": 0.0, "Neutral": 0.0,
    "Sell": -0.85, "Underweight": -0.45,
}


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
        start = end - _PERIOD_DELTAS.get(period, _PERIOD_DELTAS["1y"])
        s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    try:
        datetime.strptime(s, "%Y-%m-%d")
        datetime.strptime(e, "%Y-%m-%d")
    except ValueError as exc:
        raise MarketDataError("Tarih formatı YYYY-MM-DD olmalı") from exc
    return s, e


def _load_history(ticker: str, s: str, e: str):
    import yfinance as yf
    data = yf.Ticker(ticker).history(start=s, end=e)
    if data.empty:
        raise MarketDataError(f"{ticker} için veri bulunamadı", status_code=404)
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    return data


def _compute_candles(data) -> list[dict]:
    import numpy as np
    data["sma"] = data["Close"].rolling(window=20).mean()
    data["ema"] = data["Close"].ewm(span=20, adjust=False).mean()
    delta = data["Close"].diff()
    avg_gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    data["rsi"] = 100 - (100 / (1 + rs))
    ema_12 = data["Close"].ewm(span=12, adjust=False).mean()
    ema_26 = data["Close"].ewm(span=26, adjust=False).mean()
    data["macd_line"] = ema_12 - ema_26
    data["macd_signal"] = data["macd_line"].ewm(span=9, adjust=False).mean()
    data["macd_hist"] = data["macd_line"] - data["macd_signal"]
    data = data.replace({np.nan: None})

    def _r(value):
        return round(float(value), 2) if value is not None else None

    candles = []
    for ts, row in data.iterrows():
        candles.append({
            "time": ts.strftime("%Y-%m-%d"),
            "open": _r(row["Open"]), "high": _r(row["High"]),
            "low": _r(row["Low"]), "close": _r(row["Close"]),
            "volume": int(row.get("Volume", 0) or 0),
            "sma": _r(row["sma"]), "ema": _r(row["ema"]), "rsi": _r(row["rsi"]),
            "macd_line": _r(row["macd_line"]), "macd_signal": _r(row["macd_signal"]),
            "macd_hist": _r(row["macd_hist"]),
        })
    return candles


async def get_ohlcv(ticker: str, period: str, start_date: str | None, end_date: str | None) -> dict:
    ticker = _clean_ticker(ticker)
    s, e = _resolve_dates(period, start_date, end_date)

    def _work():
        return _compute_candles(_load_history(ticker, s, e))

    candles = await asyncio.to_thread(_work)
    return {"ticker": ticker, "start_date": s, "end_date": e, "candles": candles}


async def get_custom_indicator_series(
    ticker: str, formula: str, period: str, start_date: str | None, end_date: str | None,
) -> dict:
    ticker = _clean_ticker(ticker)
    s, e = _resolve_dates(period, start_date, end_date)

    def _work():
        import numpy as np
        from backend.services.indicator_service import evaluate_formula_safely
        data = _load_history(ticker, s, e)
        series = evaluate_formula_safely(data, formula).replace({np.nan: None})
        return [
            {"time": ts.strftime("%Y-%m-%d"),
             "value": round(float(val), 4) if val is not None else None}
            for ts, val in series.items()
        ]

    series = await asyncio.to_thread(_work)
    return {"ticker": ticker, "formula": formula, "series": series}


async def get_sentiment_history(db: AsyncSession, ticker: str) -> dict:
    ticker = _clean_ticker(ticker)
    rows = (await db.execute(
        select(AnalysisResult.trade_date, AnalysisResult.signal)
        .where(AnalysisResult.ticker == ticker)
        .order_by(AnalysisResult.trade_date.asc())
    )).all()
    history = [
        {"time": trade_date, "value": _SIGNAL_SENTIMENT.get(signal, 0.0)}
        for trade_date, signal in rows
    ]
    if not history:
        import random
        end = datetime.now()
        history = [
            {"time": (end - timedelta(days=i)).strftime("%Y-%m-%d"),
             "value": round(random.uniform(-0.6, 0.7), 2)}
            for i in range(30, -1, -1)
        ]
    return {"ticker": ticker, "history": history}
