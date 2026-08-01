import logging

from backend.services.market_data_service import get_live_prices_batch

_logger = logging.getLogger(__name__)

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
