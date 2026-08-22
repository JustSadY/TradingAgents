import json
from datetime import UTC, date, datetime, timedelta

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result, curr_date: str, *, frequency: str = "quarterly"):
    """Keep only reports that would conservatively have been public by curr_date."""
    if not curr_date:
        return result

    was_str = isinstance(result, str)
    parsed = result
    if was_str:
        try:
            parsed = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result
    if not isinstance(parsed, dict):
        return result

    cutoff = date.fromisoformat(curr_date)
    def available(report: dict, default_lag: int) -> bool:
        for field in ("acceptedDate", "filingDate", "reportedDate", "reportDate"):
            value = report.get(field)
            if value:
                try:
                    return date.fromisoformat(str(value)[:10]) <= cutoff
                except ValueError:
                    continue
        period_end = report.get("fiscalDateEnding")
        if not period_end:
            return False
        try:
            return date.fromisoformat(str(period_end)[:10]) + timedelta(days=default_lag) <= cutoff
        except ValueError:
            return False

    for key, default_lag in (("annualReports", 90), ("quarterlyReports", 45)):
        reports = parsed.get(key)
        if isinstance(reports, list):
            parsed[key] = [r for r in reports if isinstance(r, dict) and available(r, default_lag)]

    return json.dumps(parsed) if was_str else parsed


async def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    params = {
        "symbol": ticker,
    }
    result = await _make_api_request("OVERVIEW", params)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if curr_date and curr_date != today:
        warning = (
            f"# WARNING: the OVERVIEW data below is TODAY'S ({today}) live snapshot, not a "
            f"historical one as of {curr_date}. Alpha Vantage has no point-in-time OVERVIEW API — "
            "do not treat P/E, market cap, or other ratios as what they were on the analysis date.\n\n"
        )
        return warning + (result if isinstance(result, str) else json.dumps(result))
    return result

async def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    _ = freq
    result = await _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date, frequency=freq)

async def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    _ = freq
    result = await _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date, frequency=freq)

async def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    _ = freq
    result = await _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date, frequency=freq)
