"""Earnings calendar data fetching and shaping.

Extracted from ``api/earnings.py`` to keep the HTTP handler thin: all blocking
yfinance IO, parsing, and result ordering live here. The router only resolves
the ticker list and calls :func:`get_earnings_calendar`.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.utils import safe_ticker_component
from backend.models.user import User

_logger = logging.getLogger(__name__)

MAX_TICKERS = 20
_EARNINGS_FETCH_CONCURRENCY = 6

class EarningsEntry(BaseModel):
    ticker: str
    earnings_date: str | None
    eps_estimate: float | None
    reported_eps: float | None
    surprise_pct: float | None
    days_until: int | None
    status: str

def _parse_float(val: Any) -> float | None:
    """Coerce a yfinance cell to float, treating NaN/None sentinels as missing."""
    if val is None or str(val) in ("nan", "None"):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def _to_date(idx: Any) -> date | None:
    """Best-effort extraction of a ``date`` from a (possibly datetime-like) index."""
    try:
        return idx.date() if hasattr(idx, "date") else None
    except Exception:
        return None

def _earnings_date_from_calendar(ticker_obj: Any) -> date | None:
    """Read the next earnings date from ``Ticker.calendar`` (if available)."""
    try:
        calendar = ticker_obj.calendar
        if not isinstance(calendar, dict):
            return None
        raw = calendar.get("Earnings Date")
        if raw is None:
            return None
        if isinstance(raw, (list, tuple)) and len(raw) > 0:
            raw = raw[0]
        if hasattr(raw, "date"):
            return raw.date()
        if isinstance(raw, str):
            return datetime.fromisoformat(raw).date()
    except Exception as e:
        _logger.warning("Calendar lookup failed: %s", e)
    return None

def _eps_row_values(row: Any) -> tuple[float | None, float | None, float | None]:
    """Pull (eps_estimate, reported_eps, surprise_pct) out of a dataframe row."""
    return (
        _parse_float(row.get("EPS Estimate")),
        _parse_float(row.get("Reported EPS")),
        _parse_float(row.get("Surprise(%)")),
    )

def _eps_from_earnings_dates(
    ticker_obj: Any, earnings_date_val: date | None
) -> tuple[date | None, float | None, float | None, float | None]:
    """Resolve the earnings date (if still unknown) and matching EPS figures.

    Returns the (possibly updated) earnings date plus EPS estimate, reported EPS
    and surprise percentage.
    """
    eps_estimate = reported_eps = surprise_pct = None
    try:
        df = ticker_obj.get_earnings_dates(limit=4)
        if df is None or df.empty:
            return earnings_date_val, None, None, None

        if earnings_date_val is None:
            today = date.today()
            for idx in df.index:
                idx_date = _to_date(idx)
                if idx_date and idx_date >= today:
                    earnings_date_val = idx_date
                    break

        if earnings_date_val is not None:
            for idx, row in df.iterrows():
                if _to_date(idx) == earnings_date_val:
                    eps_estimate, reported_eps, surprise_pct = _eps_row_values(row)
                    break

        if eps_estimate is None and reported_eps is None and not df.empty:
            eps_estimate, reported_eps, surprise_pct = _eps_row_values(df.iloc[0])
    except Exception as e:
        _logger.warning("get_earnings_dates failed: %s", e)

    return earnings_date_val, eps_estimate, reported_eps, surprise_pct

def _compute_status(earnings_date_val: date | None) -> tuple[str | None, int | None, str]:
    """Derive (iso date string, days_until, status) from an earnings date."""
    if earnings_date_val is None:
        return None, None, "unknown"
    today = datetime.now(tz=UTC).date()
    days_until = (earnings_date_val - today).days
    status = "upcoming" if days_until >= 0 else "reported"
    return earnings_date_val.isoformat(), days_until, status

def fetch_earnings(ticker: str) -> EarningsEntry | None:
    """Blocking yfinance call — run in an executor.

    Composes the calendar lookup, EPS extraction and status computation into a
    single :class:`EarningsEntry`.
    """
    import yfinance as yf

    try:
        ticker_upper = ticker.upper()
        ticker_obj = yf.Ticker(ticker_upper)

        earnings_date_val = _earnings_date_from_calendar(ticker_obj)
        earnings_date_val, eps_estimate, reported_eps, surprise_pct = _eps_from_earnings_dates(
            ticker_obj, earnings_date_val
        )
        earnings_date_str, days_until, status = _compute_status(earnings_date_val)

        return EarningsEntry(
            ticker=ticker_upper,
            earnings_date=earnings_date_str,
            eps_estimate=eps_estimate,
            reported_eps=reported_eps,
            surprise_pct=surprise_pct,
            days_until=days_until,
            status=status,
        )
    except Exception as e:
        _logger.warning("Error fetching earnings for %s: %s", ticker, e)
        return None

def _sort_key(r: dict) -> tuple:
    """Order results: upcoming first (soonest), then reported, then unknown."""
    d = r.get("days_until")
    if d is None:
        return (2, 0)
    if d >= 0:
        return (0, d)
    return (1, -d)

async def _resolve_tickers(db: AsyncSession, user: User, tickers: str | None) -> list[str]:
    """Resolve the request's ticker list (explicit, else the user's watchlist)."""
    if tickers:
        raw_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        from backend.services.settings_service import get_or_create_settings

        settings = await get_or_create_settings(db, user)
        raw_list = list(getattr(settings, "watchlist", None) or [])

    cleaned: list[str] = []
    for t in raw_list:
        try:
            cleaned.append(safe_ticker_component(t, max_len=20))
        except Exception as _e:
            _logger.warning("Skipped invalid ticker component %r: %s", t, _e)
    return cleaned[:MAX_TICKERS]

async def get_earnings_calendar(db: AsyncSession, user: User, tickers: str | None) -> list[dict]:
    """Return earnings data for the given tickers (or the user's watchlist)."""
    cleaned = await _resolve_tickers(db, user, tickers)
    if not cleaned:
        return []

    semaphore = asyncio.Semaphore(_EARNINGS_FETCH_CONCURRENCY)

    async def _fetch_one(ticker: str):
        async with semaphore:
            return await asyncio.to_thread(fetch_earnings, ticker)

    raw_results = await asyncio.gather(*[_fetch_one(ticker) for ticker in cleaned], return_exceptions=True)

    results: list[dict] = []
    for ticker, entry in zip(cleaned, raw_results, strict=False):
        if isinstance(entry, Exception):
            _logger.warning("Failed to fetch earnings for ticker %s: %s", ticker, entry)
            continue
        if entry is None:
            continue
        results.append(entry.model_dump())

    results.sort(key=_sort_key)
    return results
