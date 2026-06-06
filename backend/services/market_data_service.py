import asyncio
import logging
import math
from typing import Optional, List, Dict
import yfinance as yf

_logger = logging.getLogger(__name__)

_BATCH_PRICE_TIMEOUT_SEC = 10.0
_SINGLE_PRICE_TIMEOUT_SEC = 6.0

async def get_live_price(ticker: str) -> Optional[float]:
    """Fetch live price for a single ticker. Falls back to history if .info is unavailable."""
    def _fetch():
        try:
            t = yf.Ticker(ticker)
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price is None:
                hist = t.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            if price is None:
                return None
            parsed = float(price)
            if not math.isfinite(parsed) or parsed <= 0:
                return None
            return parsed
        except Exception as e:
            _logger.warning("Price fetch failed for %s: %s", ticker, e)
            return None

    try:
        return await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=_SINGLE_PRICE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        _logger.warning("Price fetch timed out for %s after %.1fs", ticker, _SINGLE_PRICE_TIMEOUT_SEC)
        return None

async def get_live_prices_batch(tickers: List[str]) -> Dict[str, float]:
    """Fetch live prices for multiple tickers in a single batch call."""
    if not tickers:
        return {}
    
    unique = list(dict.fromkeys(tickers))

    def _batch_fetch():
        prices: Dict[str, float] = {}
        try:
            data = yf.download(
                unique if len(unique) > 1 else unique[0],
                period="2d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if data is None or getattr(data, "empty", False):
                return prices
            
            close = data["Close"] if "Close" in data.columns else data
            if getattr(close, "empty", False):
                return prices
            
            if hasattr(close, "columns"):
                rows = close.ffill()
                if rows.empty:
                    return prices
                last_row = rows.iloc[-1]
                for symbol in unique:
                    try:
                        raw = last_row[symbol]
                        val = float(raw)
                        if math.isfinite(val) and val > 0:
                            prices[symbol] = val
                    except (KeyError, TypeError, ValueError):
                        continue
            else:
                rows = close.ffill()
                if rows.empty:
                    return prices
                val = float(rows.iloc[-1])
                if math.isfinite(val) and val > 0:
                    prices[unique[0]] = val
        except Exception as exc:
            _logger.debug("Batch price fetch failed (%s), will fall back per-ticker: %s", unique, exc)
        return prices

    try:
        prices = await asyncio.wait_for(asyncio.to_thread(_batch_fetch), timeout=_BATCH_PRICE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        _logger.warning("Batch price fetch timed out for %s after %.1fs", unique, _BATCH_PRICE_TIMEOUT_SEC)
        prices = {}

    missing = [symbol for symbol in unique if symbol not in prices]
    if missing:
        fallbacks = await asyncio.gather(*[get_live_price(symbol) for symbol in missing], return_exceptions=True)
        for symbol, fetched in zip(missing, fallbacks):
            if isinstance(fetched, BaseException) or fetched is None:
                continue
            val = float(fetched)
            if math.isfinite(val) and val > 0:
                prices[symbol] = val
    return prices


async def get_historical_data(ticker: str, start_date: str, end_date: str):
    """Fetch historical OHLCV data for a ticker."""
    def _fetch():
        data = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if data.empty:
            return data
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)
        return data

    return await asyncio.to_thread(_fetch)
