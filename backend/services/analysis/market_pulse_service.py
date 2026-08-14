import logging
from datetime import UTC, datetime, timedelta

from backend.services.market_data_service import get_historical_data, get_live_prices_batch

_logger = logging.getLogger(__name__)


async def get_current_regime_snapshot() -> dict[str, object]:
    """Return a cheap, direction-neutral current market-regime snapshot.

    This runs before asset analysts and intentionally uses broad-market inputs
    only. S&P 500 trend supplies the market trend while live VIX defines the
    volatility/risk state. It does not inspect the asset's prior strategy or
    rating, so it can safely seed regime-aware historical weighting without
    confirmation bias. Failure returns an empty mapping and callers fall back
    to global/ticker/recent weights.
    """
    now = datetime.now(UTC)
    try:
        prices = await get_live_prices_batch(["^VIX"])
        vix = prices.get("^VIX")
        start = (now - timedelta(days=45)).date().isoformat()
        end = (now + timedelta(days=1)).date().isoformat()
        history = await get_historical_data("^GSPC", start, end)

        trend = "uncertain"
        if history is not None and not getattr(history, "empty", True) and "Close" in history:
            closes = history["Close"].dropna()
            if len(closes) >= 20:
                last = float(closes.iloc[-1])
                baseline = float(closes.tail(20).mean())
                if baseline > 0:
                    ratio = last / baseline
                    if ratio >= 1.01:
                        trend = "bull"
                    elif ratio <= 0.99:
                        trend = "bear"
                    else:
                        trend = "range_bound"

        volatility = "normal"
        risk = "neutral"
        if vix is not None:
            if vix >= 30:
                volatility = "high"
                risk = "risk_off"
            elif vix >= 20:
                volatility = "elevated"
                risk = "neutral"
            elif vix < 14:
                volatility = "low"
                risk = "risk_on"
            else:
                volatility = "normal"
                risk = "risk_on"

        # At least one real broad-market input is required. Do not create a
        # fully synthetic regime if both upstream sources failed.
        if vix is None and trend == "uncertain":
            return {}
        return {
            "trend": trend,
            "volatility": volatility,
            "risk": risk,
            "as_of": now.isoformat(),
            "source": "broad_market_v1",
        }
    except Exception as exc:  # noqa: BLE001 - regime context is optional
        _logger.warning("Could not build current market regime snapshot: %s", exc)
        return {}


async def get_market_pulse() -> str:
    """Fetch and summarize major market indicators for global context."""
    tickers = ["^GSPC", "^VIX", "BTC-USD", "GC=F"]
    names = {"^GSPC": "S&P 500", "^VIX": "VIX (Fear Index)", "BTC-USD": "Bitcoin", "GC=F": "Gold"}

    try:
        prices = await get_live_prices_batch(tickers)
        if not prices:
            return ""

        md = "=== GLOBAL MARKET PULSE ===\n"
        for ticker, price in prices.items():
            name = names.get(ticker, ticker)
            md += f"- {name}: ${price:,.2f}\n"

        vix = prices.get("^VIX")
        if vix:
            if vix > 30:
                md += "\n[MARKET ALERT] VIX is extremely high (>30). Market is in panic mode. Prioritize safety and defensive positioning.\n"
            elif vix > 20:
                md += "\n[MARKET HINT] VIX is elevated (>20). Expect increased volatility.\n"
            else:
                md += "\n[MARKET HINT] VIX is low (<20). Market sentiment is generally calm.\n"

        md += "\n"
        return md
    except Exception as e:
        _logger.warning("Could not fetch market pulse: %s", e)
        return ""