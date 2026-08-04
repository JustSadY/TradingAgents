"""Central date and point-in-time safety helpers.

Historical analyses must use a single interpretation of ``trade_date``.  This
module deliberately fails closed: malformed and future dates are rejected, and
historical-mode checks are shared by API validation, graph configuration, cache
lookups, memory recall, and tool gating.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

MAX_BACKTEST_DAYS = 3650


def parse_iso_date(value: str | date, *, field_name: str = "date", allow_future: bool = False) -> date:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a real calendar date in YYYY-MM-DD format") from exc
    else:
        raise ValueError(f"{field_name} must be a real calendar date in YYYY-MM-DD format")

    if not allow_future and parsed > datetime.now(UTC).date():
        raise ValueError(f"{field_name} cannot be in the future")
    return parsed


def normalize_iso_date(value: str | date, *, field_name: str = "date", allow_future: bool = False) -> str:
    return parse_iso_date(value, field_name=field_name, allow_future=allow_future).isoformat()


def is_historical_trade_date(value: str | date, *, today: date | None = None) -> bool:
    parsed = parse_iso_date(value, field_name="trade_date", allow_future=False)
    return parsed < (today or datetime.now(UTC).date())


def validate_date_range(
    start_date: str | date,
    end_date: str | date,
    *,
    max_days: int = MAX_BACKTEST_DAYS,
    allow_future_end: bool = False,
) -> tuple[str, str]:
    start = parse_iso_date(start_date, field_name="start_date", allow_future=allow_future_end)
    end = parse_iso_date(end_date, field_name="end_date", allow_future=allow_future_end)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    span = (end - start).days
    if span > max_days:
        raise ValueError(f"date range cannot exceed {max_days} days")
    return start.isoformat(), end.isoformat()
