from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, Request

from backend.api.deps import require_any_page
from backend.core.limiter import limiter
from backend.models.user import User

router = APIRouter(prefix="/api/market", tags=["market"])
_logger = logging.getLogger(__name__)

_cache: dict = {"rates": {}, "ts": 0.0}
_CACHE_TTL = 3600

SUPPORTED_CURRENCIES = {
    "USD": 1.0,
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
        except Exception as exc:
            _logger.debug("Failed to fetch FX rate for %s: %s", symbol, exc)
            return symbol, None

    pairs = await asyncio.gather(*[_one(sym) for sym in symbols])

    sym_to_rate = dict(pairs)

    rates: dict[str, float] = {"USD": 1.0}
    for currency, symbol in SUPPORTED_CURRENCIES.items():
        if currency == "USD":
            continue
        rate = sym_to_rate.get(symbol)
        if rate is not None:
            rates[currency] = round(rate, 6)

    return rates

@router.get("/fx-rates", response_model=dict[str, float | None])
@limiter.limit("30/minute")
async def get_fx_rates(
    request: Request,
    _: User = Depends(require_any_page("dashboard", "portfolio", "chart")),
):
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

    result = {}
    for currency in SUPPORTED_CURRENCIES:
        result[currency] = _cache["rates"].get(currency)
    result["USD"] = 1.0
    return result
