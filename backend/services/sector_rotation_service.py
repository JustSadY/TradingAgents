import asyncio
import time
from typing import Any

import numpy as np
import yfinance as yf

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

_cache: dict[str, Any] = {}
_CACHE_TTL = 1800  # 30 min


def _rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    arr = np.array(prices, dtype=float)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:]))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1 + rs)


async def get_sector_rotation() -> list[dict[str, Any]]:
    now = time.time()
    cached = _cache.get("sector_rotation")
    if cached and now - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    tickers = list(SECTORS.keys())

    def _fetch() -> Any:
        return yf.download(
            tickers,
            period="6mo",
            progress=False,
            auto_adjust=True,
            threads=False,
        )

    loop = asyncio.get_event_loop()
    max_retries = 3
    delay = 1.0
    raw = None
    for attempt in range(max_retries):
        try:
            raw = await loop.run_in_executor(None, _fetch)
            if raw is not None and not getattr(raw, "empty", False):
                break
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                raise

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
        except Exception:
            continue

    results.sort(key=lambda x: x["momentum_score"], reverse=True)
    _cache["sector_rotation"] = {"ts": now, "data": results}
    return results
