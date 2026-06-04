import io
import logging
from datetime import datetime, timedelta
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.api.deps import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.analysis import AnalysisResult
_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market", tags=["market"])
def _date_range(period: str) -> tuple[str, str]:
    end = datetime.now()
    delta_map = {
        "1m": timedelta(days=31),
        "3m": timedelta(days=92),
        "6m": timedelta(days=183),
        "1y": timedelta(days=365),
        "2y": timedelta(days=730),
        "5y": timedelta(days=1825),
    }
    delta = delta_map.get(period, timedelta(days=365))
    start = end - delta
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
@router.get("/ohlcv")
async def get_ohlcv(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    period: str = Query("1y", description="1m|3m|6m|1y|2y|5y — ignored when start_date provided"),
    _: dict = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    if start_date and end_date:
        s, e = start_date, end_date
    else:
        s, e = _date_range(period)
    try:
        datetime.strptime(s, "%Y-%m-%d")
        datetime.strptime(e, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Tarih formatı YYYY-MM-DD olmalı")
    try:
        import yfinance as yf
        data = yf.Ticker(ticker).history(start=s, end=e)
        if data.empty:
            raise HTTPException(status_code=404, detail=f"{ticker} için veri bulunamadı")
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        data["sma"] = data["Close"].rolling(window=20).mean()
        data["ema"] = data["Close"].ewm(span=20, adjust=False).mean()
        delta = data["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        data["rsi"] = 100 - (100 / (1 + rs))
        ema_12 = data["Close"].ewm(span=12, adjust=False).mean()
        ema_26 = data["Close"].ewm(span=26, adjust=False).mean()
        data["macd_line"] = ema_12 - ema_26
        data["macd_signal"] = data["macd_line"].ewm(span=9, adjust=False).mean()
        data["macd_hist"] = data["macd_line"] - data["macd_signal"]
        import numpy as np
        data = data.replace({np.nan: None})
        candles = []
        for ts, row in data.iterrows():
            candles.append({
                "time": ts.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row.get("Volume", 0)),
                "sma": round(float(row["sma"]), 2) if row["sma"] is not None else None,
                "ema": round(float(row["ema"]), 2) if row["ema"] is not None else None,
                "rsi": round(float(row["rsi"]), 2) if row["rsi"] is not None else None,
                "macd_line": round(float(row["macd_line"]), 2) if row["macd_line"] is not None else None,
                "macd_signal": round(float(row["macd_signal"]), 2) if row["macd_signal"] is not None else None,
                "macd_hist": round(float(row["macd_hist"]), 2) if row["macd_hist"] is not None else None,
            })
        return {"ticker": ticker, "start_date": s, "end_date": e, "candles": candles}
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("OHLCV fetch failed %s: %s", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))
@router.get("/sentiment-history")
async def get_sentiment_history(
    ticker: str = Query(..., description="Ticker symbol, e.g. AAPL"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    ticker = ticker.upper().strip()
    q = (
        select(AnalysisResult.trade_date, AnalysisResult.signal)
        .where(AnalysisResult.ticker == ticker)
        .order_by(AnalysisResult.trade_date.asc())
    )
    res = await db.execute(q)
    rows = res.all()
    mapping = {
        "Buy": 0.85, "Overweight": 0.45, "Hold": 0.0, "Neutral": 0.0,
        "Sell": -0.85, "Underweight": -0.45,
    }
    history = []
    for r in rows:
        trade_date = r[0]
        signal = r[1]
        score = mapping.get(signal, 0.0)
        history.append({
            "time": trade_date,
            "value": score,
        })
    if not history:
        import random
        from datetime import datetime, timedelta
        end = datetime.now()
        for i in range(30, -1, -1):
            dt = end - timedelta(days=i)
            history.append({
                "time": dt.strftime("%Y-%m-%d"),
                "value": round(random.uniform(-0.6, 0.7), 2),
            })
    return {"ticker": ticker, "history": history}
