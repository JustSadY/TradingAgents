from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter

router = APIRouter(prefix="/api/market", tags=["market"])
_logger = logging.getLogger(__name__)

# Simple in-memory cache: rates are refreshed at most once per hour
_cache: dict = {"rates": {}, "ts": 0.0}
_CACHE_TTL = 3600  # 1 hour

SUPPORTED_CURRENCIES = {
    "USD": 1.0,  # base
    "EUR": "EURUSD=X",
    "GBP": "GBPUSD=X",
    "JPY": "JPYUSD=X",
    "TRY": "TRYUSD=X",
    "CAD": "CADUSD=X",
    "AUD": "AUDUSD=X",
    "CHF": "CHFUSD=X",
}


async def _fetch_rates() -> dict[str, float]:
    """Fetch current FX rates vs USD using yfinance. Returns {currency: rate_vs_usd}."""
    symbols = [sym for sym in SUPPORTED_CURRENCIES.values() if isinstance(sym, str)]

    async def _one(symbol: str) -> tuple[str, float | None]:
        try:
            import yfinance as yf

            hist = await asyncio.to_thread(lambda s=symbol: yf.Ticker(s).history(period="2d")["Close"])
            if hist.empty:
                return symbol, None
            return symbol, float(hist.iloc[-1])
        except Exception:
            return symbol, None

    pairs = await asyncio.gather(*[_one(sym) for sym in symbols])

    # Build currency → USD rate mapping
    # Note: EURUSD=X gives EUR per 1 USD, but actually yfinance gives the price of 1 EUR in USD
    # So EURUSD=X = 1.08 means 1 EUR = 1.08 USD
    # We want: how many USD is 1 [currency]? → that IS the EURUSD=X value
    # For inverse pairs like JPYUSD=X: yfinance gives 1 JPY in USD (e.g. 0.0067)
    sym_to_rate = dict(pairs)

    rates: dict[str, float] = {"USD": 1.0}
    for currency, symbol in SUPPORTED_CURRENCIES.items():
        if currency == "USD":
            continue
        rate = sym_to_rate.get(symbol)
        if rate:
            rates[currency] = round(rate, 6)

    return rates


@router.get("/fx-rates")
async def get_fx_rates():
    """
    Returns exchange rates vs USD for supported currencies.
    Response: {"USD": 1.0, "EUR": 1.085, "GBP": 1.27, ...}
    Cached for 1 hour.
    """
    now = time.time()
    if now - _cache["ts"] > _CACHE_TTL or not _cache["rates"]:
        rates = await _fetch_rates()
        if rates:
            _cache["rates"] = rates
            _cache["ts"] = now

    # Return cached rates, fill missing with None
    result = {}
    for currency in SUPPORTED_CURRENCIES:
        result[currency] = _cache["rates"].get(currency)
    result["USD"] = 1.0
    return result
