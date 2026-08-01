from backend.trading_agents.dataflows.y_finance import _format_usd_amount


def test_formats_large_yahoo_monetary_values_with_the_correct_unit():
    assert _format_usd_amount(253_500_000_000) == "$253.50B USD"
    assert _format_usd_amount(96_700_000) == "$96.70M USD"
    assert _format_usd_amount(-1_500_000_000) == "$-1.50B USD"
