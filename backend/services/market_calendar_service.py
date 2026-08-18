"""Exchange trading-day awareness for scheduled and automated work.

Scheduled watchlist scans and automated orders used to run on any calendar
day. On an exchange holiday that means burning an analysis run on stale
quotes and, worse, letting the bot emit sell orders into a market that
cannot fill them.

``exchange_calendars`` owns the holiday data. This module maps a ticker (or
an explicit asset type) onto one of its calendars and answers a single
question: is the exchange open on this date?

Two deliberate choices:

* **Crypto is always open.** It has no exchange calendar, and gating it on
  XNYS holidays would be wrong.
* **Lookups fail open.** A missing package, an unknown calendar code, or a
  date outside the calendar's bounds returns "open" and logs a warning. A
  calendar problem must never be able to freeze every user's automation.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any

_logger = logging.getLogger(__name__)

DEFAULT_EQUITY_CALENDAR = "XNYS"

# Suffixed tickers name their listing venue directly (yfinance convention).
_SUFFIX_CALENDARS: dict[str, str] = {
    ".AS": "XAMS",
    ".AX": "XASX",
    ".BO": "XBOM",
    ".BR": "XBRU",
    ".CO": "XCSE",
    ".DE": "XETR",
    ".F": "XFRA",
    ".HE": "XHEL",
    ".HK": "XHKG",
    ".IS": "XIST",
    ".JO": "XJSE",
    ".KS": "XKRX",
    ".L": "XLON",
    ".LS": "XLIS",
    ".MC": "XMAD",
    ".MI": "XMIL",
    ".MX": "XMEX",
    ".NZ": "XNZE",
    ".OL": "XOSL",
    ".PA": "XPAR",
    ".SA": "BVMF",
    ".SI": "XSES",
    ".SS": "XSHG",
    ".ST": "XSTO",
    ".SW": "XSWX",
    ".T": "XTKS",
    ".TA": "XTAE",
    ".TO": "XTSE",
    ".TW": "XTAI",
    ".VI": "XWBO",
    ".WA": "XWAR",
}

_CRYPTO_QUOTE_SUFFIXES = ("-USD", "-USDT", "-USDC", "-EUR", "-BUSD", "-GBP", "USDT", "USDC")
_CRYPTO_BASE_SYMBOLS = frozenset(
    {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC", "LTC", "LINK", "BNB", "TRX", "TON"}
)
_TICKER_SUFFIX = re.compile(r"(\.[A-Za-z]{1,3})$")


def looks_like_crypto(ticker: str | None) -> bool:
    """Whether a bare ticker names a 24/7 crypto pair rather than a listing."""
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return False
    if symbol.endswith(_CRYPTO_QUOTE_SUFFIXES):
        return True
    return symbol in _CRYPTO_BASE_SYMBOLS


def calendar_code_for(ticker: str | None = None, asset_type: str | None = None) -> str | None:
    """Return the exchange calendar for an instrument, or ``None`` when 24/7.

    ``asset_type`` wins when it says crypto; otherwise the ticker suffix picks
    the venue and everything unsuffixed falls back to the configured default
    equity calendar.
    """
    if (asset_type or "").strip().lower() in {"crypto", "cryptocurrency"}:
        return None
    if looks_like_crypto(ticker):
        return None

    symbol = (ticker or "").strip().upper()
    match = _TICKER_SUFFIX.search(symbol)
    if match:
        mapped = _SUFFIX_CALENDARS.get(match.group(1))
        if mapped:
            return mapped

    return _default_equity_calendar()


def _default_equity_calendar() -> str:
    try:
        from backend.core.config import get_settings

        configured = (get_settings().DEFAULT_EXCHANGE_CALENDAR or "").strip().upper()
    except Exception:  # noqa: BLE001 — never let configuration break a gate
        return DEFAULT_EQUITY_CALENDAR
    return configured or DEFAULT_EQUITY_CALENDAR


@lru_cache(maxsize=32)
def _calendar(code: str) -> Any | None:
    """Load and cache one exchange calendar; ``None`` when it is unavailable."""
    try:
        import exchange_calendars as xcals

        return xcals.get_calendar(code)
    except Exception as exc:  # noqa: BLE001 — unknown code, missing package, bad bounds
        _logger.warning("Exchange calendar %s is unavailable (%s); treating the market as open.", code, exc)
        return None


def is_trading_day(day: date, *, ticker: str | None = None, asset_type: str | None = None) -> bool:
    """Whether the instrument's exchange holds a session on ``day``."""
    code = calendar_code_for(ticker, asset_type)
    if code is None:
        return True

    calendar = _calendar(code)
    if calendar is None:
        return True

    try:
        import pandas as pd

        return bool(calendar.is_session(pd.Timestamp(day)))
    except Exception as exc:  # noqa: BLE001 — out-of-bounds dates and pandas issues fail open
        _logger.warning("Trading-day lookup failed for %s on %s (%s); treating it as open.", code, day, exc)
        return True


def next_trading_day(day: date, *, ticker: str | None = None, asset_type: str | None = None) -> date | None:
    """The first session on or after ``day``, or ``None`` when unavailable."""
    code = calendar_code_for(ticker, asset_type)
    if code is None:
        return day

    calendar = _calendar(code)
    if calendar is None:
        return None

    try:
        import pandas as pd

        timestamp = pd.Timestamp(day)
        if calendar.is_session(timestamp):
            return day
        return calendar.date_to_session(timestamp, direction="next").date()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Next-session lookup failed for %s from %s (%s).", code, day, exc)
        return None


def market_closed_reason(
    day: date | None = None,
    *,
    ticker: str | None = None,
    asset_type: str | None = None,
) -> str | None:
    """A human-readable reason when the exchange is shut, else ``None``.

    Callers use the truthiness as the gate and the text as the skip message,
    so there is one place deciding both.
    """
    target = day or datetime.now().date()
    if is_trading_day(target, ticker=ticker, asset_type=asset_type):
        return None

    code = calendar_code_for(ticker, asset_type) or DEFAULT_EQUITY_CALENDAR
    following = next_trading_day(target, ticker=ticker, asset_type=asset_type)
    if following and following != target:
        return f"{code} is closed on {target.isoformat()}; the next session is {following.isoformat()}."
    return f"{code} is closed on {target.isoformat()}."
