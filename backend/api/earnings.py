import asyncio
import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.core.limiter import limiter
from backend.core.utils import safe_ticker_component
from backend.models.user import User

router = APIRouter(prefix="/api/market", tags=["earnings"])

_logger = logging.getLogger(__name__)

MAX_TICKERS = 20


class EarningsEntry(BaseModel):
    ticker: str
    earnings_date: str | None
    eps_estimate: float | None
    reported_eps: float | None
    surprise_pct: float | None
    days_until: int | None
    status: str  # "upcoming" | "reported" | "unknown"


def _fetch_earnings(ticker: str) -> EarningsEntry | None:
    """Blocking yfinance call — run in executor."""
    import yfinance as yf

    try:
        ticker_upper = ticker.upper()
        ticker_obj = yf.Ticker(ticker_upper)

        # ------------------------------------------------------------------
        # 1. Determine the next earnings date from .calendar
        # ------------------------------------------------------------------
        earnings_date_val: date | None = None
        try:
            calendar = ticker_obj.calendar
            if isinstance(calendar, dict):
                raw = calendar.get("Earnings Date")
                if raw is not None:
                    if isinstance(raw, (list, tuple)) and len(raw) > 0:
                        raw = raw[0]
                    if hasattr(raw, "date"):
                        earnings_date_val = raw.date()
                    elif isinstance(raw, str):
                        earnings_date_val = datetime.fromisoformat(raw).date()
        except Exception as e:
            _logger.debug("calendar lookup failed for %s: %s", ticker_upper, e)

        # ------------------------------------------------------------------
        # 2. EPS data from get_earnings_dates
        # ------------------------------------------------------------------
        eps_estimate: float | None = None
        reported_eps: float | None = None
        surprise_pct: float | None = None

        try:
            df = ticker_obj.get_earnings_dates(limit=4)
            if df is not None and not df.empty:
                # If we don't have a date from calendar yet, grab the first
                # upcoming date from this DataFrame (index is datetime)
                if earnings_date_val is None:
                    today = date.today()
                    for idx in df.index:
                        try:
                            idx_date = idx.date() if hasattr(idx, "date") else None
                        except Exception:
                            idx_date = None
                        if idx_date and idx_date >= today:
                            earnings_date_val = idx_date
                            break

                # Match the row closest to our earnings_date_val for EPS data
                if earnings_date_val is not None:
                    for idx, row in df.iterrows():
                        try:
                            idx_date = idx.date() if hasattr(idx, "date") else None
                        except Exception:
                            idx_date = None
                        if idx_date == earnings_date_val:
                            est = row.get("EPS Estimate")
                            rep = row.get("Reported EPS")
                            sur = row.get("Surprise(%)")
                            eps_estimate = float(est) if est is not None and str(est) not in ("nan", "None") else None
                            reported_eps = float(rep) if rep is not None and str(rep) not in ("nan", "None") else None
                            surprise_pct = float(sur) if sur is not None and str(sur) not in ("nan", "None") else None
                            break

                # Fallback: grab first row for EPS if nothing matched by date
                if eps_estimate is None and reported_eps is None and not df.empty:
                    row = df.iloc[0]
                    est = row.get("EPS Estimate")
                    rep = row.get("Reported EPS")
                    sur = row.get("Surprise(%)")
                    eps_estimate = float(est) if est is not None and str(est) not in ("nan", "None") else None
                    reported_eps = float(rep) if rep is not None and str(rep) not in ("nan", "None") else None
                    surprise_pct = float(sur) if sur is not None and str(sur) not in ("nan", "None") else None
        except Exception as e:
            _logger.debug("get_earnings_dates failed for %s: %s", ticker_upper, e)

        # ------------------------------------------------------------------
        # 3. Compute days_until and status
        # ------------------------------------------------------------------
        earnings_date_str: str | None = None
        days_until: int | None = None
        status = "unknown"

        if earnings_date_val is not None:
            earnings_date_str = earnings_date_val.isoformat()
            today = datetime.now(tz=UTC).date()
            days_until = (earnings_date_val - today).days
            status = "upcoming" if days_until >= 0 else "reported"

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


@router.get("/earnings-calendar")
@limiter.limit("20/minute")
async def earnings_calendar(
    request: Request,
    tickers: str | None = Query(
        default=None,
        description="Comma-separated tickers. Defaults to user's watchlist.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return upcoming earnings data for the given tickers (or user watchlist)."""

    # Resolve ticker list
    if tickers:
        raw_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        from backend.services.settings_service import get_or_create_settings

        settings = await get_or_create_settings(db, current_user)
        raw_list = list(getattr(settings, "watchlist", None) or [])

    # Sanitise and cap
    cleaned: list[str] = []
    for t in raw_list:
        try:
            cleaned.append(safe_ticker_component(t, max_len=20))
        except Exception:
            pass
    cleaned = cleaned[:MAX_TICKERS]

    if not cleaned:
        return {"results": []}

    # Fetch earnings concurrently in the thread pool
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _fetch_earnings, ticker) for ticker in cleaned]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict] = []
    for entry in raw_results:
        if isinstance(entry, Exception) or entry is None:
            continue
        results.append(entry.model_dump())

    # Sort: upcoming first (soonest), then reported, then unknown
    def sort_key(r: dict) -> tuple:
        d = r.get("days_until")
        if d is None:
            return (2, 0)
        if d >= 0:
            return (0, d)
        return (1, -d)

    results.sort(key=sort_key)

    return {"results": results}
