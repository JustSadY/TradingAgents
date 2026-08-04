from datetime import UTC, datetime, timedelta

import pytest

from backend.core.temporal import normalize_iso_date, validate_date_range
from backend.schemas.analysis import AnalysisRunRequest, TimeTravelRequest


def test_real_calendar_date_is_required():
    with pytest.raises(ValueError):
        normalize_iso_date("2026-02-30")


def test_future_trade_date_is_rejected():
    future = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        AnalysisRunRequest(ticker="AAPL", trade_date=future, asset_type="stock")


def test_date_range_must_be_ordered_and_bounded():
    with pytest.raises(ValueError, match="on or before"):
        validate_date_range("2025-02-01", "2025-01-01")
    with pytest.raises(ValueError, match="cannot exceed"):
        validate_date_range("2010-01-01", "2025-01-01", max_days=3650)


def test_time_travel_rejects_protected_and_unknown_fields():
    with pytest.raises(ValueError):
        TimeTravelRequest(checkpoint_id="cp", update_state={"trade_date": "2020-01-01"})
    with pytest.raises(ValueError):
        TimeTravelRequest(checkpoint_id="cp", update_state={"arbitrary": "value"})
