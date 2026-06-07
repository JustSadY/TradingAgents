import json

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result, curr_date: str):
    """Drop reports dated after ``curr_date`` to avoid look-ahead bias.

    ``_make_api_request`` returns the raw response *text* (a JSON string), so we
    parse it before filtering and re-serialize, returning the same type we were
    given. Previously this only handled ``dict`` and therefore never ran on the
    string it actually received, leaking future-dated statements into backtests.
    """
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

    for key in ("annualReports", "quarterlyReports"):
        reports = parsed.get(key)
        if isinstance(reports, list):
            parsed[key] = [r for r in reports if r.get("fiscalDateEnding", "") <= curr_date]

    return json.dumps(parsed) if was_str else parsed


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    params = {
        "symbol": ticker,
    }
    return _make_api_request("OVERVIEW", params)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    result = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    result = _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    result = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)
