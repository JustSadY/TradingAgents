import asyncio
import logging
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from cachetools import TTLCache
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

from backend.services.indicator_service import calculate_rsi

_logger = logging.getLogger(__name__)


class _EmptyDownload(Exception):
    """An empty frame is retried like a failure but is not an error to report."""

SECTORS: dict[str, str] = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Consumer Disc.",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication",
}

_CACHE_TTL = 1800
_cache: TTLCache = TTLCache(maxsize=1, ttl=_CACHE_TTL)

def _rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    closes = pd.Series(prices)
    rsi_series = calculate_rsi(closes, period)
    if rsi_series.empty:
        return 50.0
    value = rsi_series.iloc[-1]
    return float(value) if not np.isnan(value) else 50.0

async def get_sector_rotation() -> list[dict[str, Any]]:
    cached = _cache.get("sector_rotation")
    if cached is not None:
        return cached

    tickers = list(SECTORS.keys())

    def _fetch() -> Any:
        return yf.download(
            tickers,
            period="6mo",
            progress=False,
            auto_adjust=True,
            threads=False,
        )

    loop = asyncio.get_running_loop()
    raw = None
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1.0, max=10.0),
            reraise=True,
        ):
            with attempt:
                raw = await loop.run_in_executor(None, _fetch)
                if raw is None or getattr(raw, "empty", False):
                    raise _EmptyDownload
    except _EmptyDownload:
        return []

    results: list[dict[str, Any]] = []
    for ticker, name in SECTORS.items():
        try:
            closes = raw["Close"][ticker].dropna()
            volumes = raw["Volume"][ticker].dropna()
            prices = [float(p) for p in closes.tolist()]
            vols = [float(v) for v in volumes.tolist()]
            if len(prices) < 22:
                continue

            now_price = prices[-1]
            ret_1w = (now_price / prices[-6] - 1) * 100 if len(prices) >= 6 else 0.0
            ret_1m = (now_price / prices[-22] - 1) * 100
            ret_3m = (now_price / prices[-66] - 1) * 100 if len(prices) >= 66 else 0.0

            rsi = _rsi(prices)
            sma20 = float(np.mean(prices[-20:]))
            above_sma = now_price > sma20

            avg_vol = float(np.mean(vols[-20:])) if vols else 1.0
            vol_ratio = vols[-1] / avg_vol if avg_vol > 0 else 1.0

            raw_mom = ret_1w * 0.4 + ret_1m * 0.35 + ret_3m * 0.25
            momentum_score = max(-1.0, min(1.0, raw_mom / 15.0))

            results.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "price": round(now_price, 2),
                    "ret_1w": round(ret_1w, 2),
                    "ret_1m": round(ret_1m, 2),
                    "ret_3m": round(ret_3m, 2),
                    "rsi": round(rsi, 1),
                    "above_sma20": above_sma,
                    "volume_ratio": round(vol_ratio, 2),
                    "momentum_score": round(momentum_score, 3),
                }
            )
        except Exception as _e:
            _logger.debug("Failed processing sector ticker %s: %s", ticker, _e)
            continue

    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    if results:
        _cache["sector_rotation"] = results
    return results
