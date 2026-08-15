from backend.trading_agents.agents.utils.agent_utils import build_instrument_context


def test_us_equity_context_keeps_quote_currency_independent_of_report_language():
    context = build_instrument_context("NVDA")

    assert "USD" in context
    assert "TL/TRY" in context

def test_borsa_istanbul_context_marks_try_quote_currency():
    context = build_instrument_context("ASELS.IS")

    assert "TRY" in context
