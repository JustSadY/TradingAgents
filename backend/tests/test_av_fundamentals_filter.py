"""Regression test for Alpha Vantage fundamentals look-ahead filtering.

_make_api_request returns the raw response *text* (a JSON string), but the
date filter used to only handle dicts, so it never ran and future-dated
statements leaked into backtests.
"""

import json

from backend.trading_agents.dataflows.alpha_vantage_fundamentals import _filter_reports_by_date

_PAYLOAD = json.dumps(
    {
        "symbol": "AAPL",
        "quarterlyReports": [
            {"fiscalDateEnding": "2023-12-31", "value": 1},
            {"fiscalDateEnding": "2024-03-31", "value": 2},
            {"fiscalDateEnding": "2024-09-30", "value": 3},  # after curr_date
        ],
    }
)


def test_string_payload_is_filtered_and_stays_a_string():
    out = _filter_reports_by_date(_PAYLOAD, "2024-06-15")
    assert isinstance(out, str)
    dates = [r["fiscalDateEnding"] for r in json.loads(out)["quarterlyReports"]]
    assert dates == ["2023-12-31", "2024-03-31"]


def test_no_curr_date_is_passthrough():
    assert _filter_reports_by_date(_PAYLOAD, None) == _PAYLOAD


def test_malformed_json_is_returned_unchanged():
    assert _filter_reports_by_date("not json at all", "2024-06-15") == "not json at all"
