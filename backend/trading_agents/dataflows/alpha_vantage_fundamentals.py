from .alpha_vantage_common import _make_api_request
def _filter_reports_by_date(result, curr_date: str):
    if not curr_date or not isinstance(result, dict):
        return result
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r for r in result[key]
                if r.get("fiscalDateEnding", "") <= curr_date
            ]
    return result
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
