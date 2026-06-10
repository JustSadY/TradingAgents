"""Tests for the signal-replay backtest context rendering."""

from types import SimpleNamespace

from backend.services.signal_backtest_service import render_signal_replay


def _row(signal, raw_return, trade_date="2025-01-01"):
    return SimpleNamespace(signal=signal, raw_return=raw_return, trade_date=trade_date)


def test_empty_history_renders_nothing():
    assert render_signal_replay("AAPL", []) == ""
    # Rows without realized returns are also ignored.
    assert render_signal_replay("AAPL", [_row("Buy", None)]) == ""


def test_buy_win_rate_counts_positive_returns():
    rows = [_row("Buy", 5.0), _row("Buy", -2.0), _row("Buy", 3.0)]
    md = render_signal_replay("AAPL", rows)
    assert "SIGNAL REPLAY BACKTEST FOR AAPL" in md
    # 2 of 3 positive → 67% win rate, avg +2.00%
    assert "Buy: 3 signal(s)" in md
    assert "win rate 67%" in md
    assert "avg realized return +2.00%" in md


def test_sell_win_means_price_fell():
    # A Sell call is correct when the realized return is negative.
    rows = [_row("Sell", -4.0), _row("Sell", 2.0)]
    md = render_signal_replay("TSLA", rows)
    assert "Sell: 2 signal(s)" in md
    assert "win rate 50%" in md


def test_recent_calls_listed():
    rows = [_row("Buy", 1.5, "2025-03-01"), _row("Hold", 0.2, "2025-02-01")]
    md = render_signal_replay("MSFT", rows)
    assert "2025-03-01: Buy -> +1.50%" in md
    assert "2025-02-01: Hold -> +0.20%" in md
