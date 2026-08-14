"""End-to-end execution semantics of the backtest engine.

The unit tests next to this file cover slippage direction, P&L and commission
legs. What was untested is the property that decides whether a backtest result
means anything at all: **when** a signal may be acted on, and at which price.

A strategy that reacts to a bar it could not have seen produces a profitable
backtest and a losing live strategy, and nothing about the output looks wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from backend.services import backtest_service as bt


def _bars(closes: list[float], *, opens: list[float] | None = None) -> pd.DataFrame:
    """Daily bars with a deliberate open/close gap so fills are distinguishable."""
    opens = opens if opens is not None else [c - 5 for c in closes]
    return pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "Open": opens,
            "High": [max(o, c) + 1 for o, c in zip(opens, closes, strict=True)],
            "Low": [min(o, c) - 1 for o, c in zip(opens, closes, strict=True)],
            "Close": closes,
            "Volume": [1_000.0] * len(closes),
        }
    )


@pytest.fixture
def rsi_bars() -> pd.DataFrame:
    """Rally into overbought, then a decline that crosses down through 30.

    A monotonic decline is no good: with no gains at all the RSI guard pins the
    series straight to 0 and it never *crosses* 30 from above.
    """
    closes = [100.0 + i for i in range(20)] + [119.0 - i * 1.5 for i in range(40)]
    return _bars(closes)


async def _run(monkeypatch, bars: pd.DataFrame, **kwargs) -> dict:
    """Run a full simulation against fixed bars, with no network or database."""
    monkeypatch.setattr(bt, "load_ohlcv", lambda *_a, **_k: bars.copy())

    async def _no_benchmark(*_a, **_k):
        return None

    monkeypatch.setattr(bt, "_benchmark_return", _no_benchmark)

    params = {
        "ticker": "TEST",
        "strategy_type": "rsi_oversold",
        "start_date": bars["Date"].iloc[25].strftime("%Y-%m-%d"),
        "end_date": bars["Date"].iloc[-1].strftime("%Y-%m-%d"),
        "initial_capital": 100_000.0,
        "slippage_bps": 0,
    }
    params.update(kwargs)
    return await bt.run_backtest_simulation(db=None, **params)


async def test_entries_fill_at_the_open_after_the_signal_bar(monkeypatch, rsi_bars):
    """The decisive property: a signal is filled on the *following* bar's open.

    The strategy reads the previous, already-closed bar and trades at the next
    open. Filling on the signal bar's own close would let it act on information
    it did not have, which is the difference between a backtest that means
    something and one that does not.
    """
    result = await _run(monkeypatch, rsi_bars)

    assert "error" not in result, result
    assert result["trades"], "fixture produced no trades"

    by_date = {d.strftime("%Y-%m-%d"): (o, c) for d, o, c in
               zip(rsi_bars["Date"], rsi_bars["Open"], rsi_bars["Close"], strict=True)}

    for trade in result["trades"]:
        entry_open, entry_close = by_date[trade["entry_date"]]
        # Slippage is zero here, so the fill must be exactly the bar's open.
        assert trade["entry_price"] == pytest.approx(entry_open), trade
        assert trade["entry_price"] != pytest.approx(entry_close), trade


async def test_a_later_end_date_never_changes_earlier_trades(monkeypatch, rsi_bars):
    """Extending the window must not rewrite history.

    If any calculation reached forward, adding future bars would change trades
    that already happened.
    """
    short_end = rsi_bars["Date"].iloc[45].strftime("%Y-%m-%d")
    truncated = await _run(monkeypatch, rsi_bars, end_date=short_end)
    full = await _run(monkeypatch, rsi_bars)

    assert "error" not in truncated and "error" not in full
    overlap = [t for t in full["trades"] if t["entry_date"] <= short_end]
    assert truncated["trades"] == overlap[: len(truncated["trades"])]


async def test_first_bar_cannot_trade(rsi_bars):
    """There is no previous bar to derive a signal from."""
    data = bt._prepare_data(rsi_bars.copy(), "rsi_oversold")
    signal, _, _ = bt._generate_signal(data, data.loc[0], "rsi_oversold", {})
    assert signal is None


def test_indicators_are_computed_before_the_window_is_cut(rsi_bars):
    """Warm-up bars must precede the tested window.

    ``_prepare_data`` runs on the full series and the date filter is applied
    afterwards; computing indicators on the trimmed window would leave the first
    trading days with NaN or, worse, differently-seeded values.
    """
    data = bt._prepare_data(rsi_bars.copy(), "rsi_oversold")
    assert data["rsi"].notna().any()
    assert data["rsi"].isna().sum() > 0  # a real warm-up exists
    assert len(data) == len(rsi_bars)


class TestSlippageDirection:
    """Slippage always costs the trader, on both sides and both directions."""

    def test_buy_fills_above_the_reference_price(self):
        filled = bt._apply_slippage_decimal(Decimal("100"), "BUY", Decimal("50"))
        assert filled > Decimal("100")

    def test_sell_fills_below_the_reference_price(self):
        filled = bt._apply_slippage_decimal(Decimal("100"), "SELL", Decimal("50"))
        assert filled < Decimal("100")

    def test_a_round_trip_never_profits_from_slippage(self):
        """Entering and exiting at the same quote must lose the spread twice."""
        quote = Decimal("100")
        bps = Decimal("50")
        entry = bt._apply_slippage_decimal(quote, "BUY", bps)
        exit_ = bt._apply_slippage_decimal(quote, "SELL", bps)
        assert exit_ < entry


def test_short_financing_reduces_realised_pnl():
    """Borrow cost is deducted from the trade, not silently dropped.

    The run loop accrues it daily; this pins that the accumulated figure
    actually reaches P&L, so a short held longer is worth less.
    """
    args = ("short", Decimal("100"), Decimal("90"), Decimal("10"), Decimal("0.001"))
    free = bt._trade_pnl_decimal(*args, Decimal("0"))
    one_day = bt._trade_pnl_decimal(*args, bt._money(Decimal("100") * 10 * bt._SHORT_BORROW_APR / Decimal(252)))
    ten_days = bt._trade_pnl_decimal(*args, bt._money(Decimal("100") * 10 * bt._SHORT_BORROW_APR / Decimal(252)) * 10)

    assert free > one_day > ten_days


def test_exit_levels_are_directionally_valid_for_a_short():
    """A long-shaped analyst plan must not become an inverted short bracket.

    A stop below the entry on a short would be a take-profit, so the engine
    replaces nonsensical levels rather than trusting the annotation.
    """
    stop, target = bt._normalise_exit_levels("short", Decimal("100"), 90, 110)

    assert stop > Decimal("100")
    assert target < Decimal("100")


def test_exit_levels_are_directionally_valid_for_a_long():
    stop, target = bt._normalise_exit_levels("long", Decimal("100"), 110, 90)

    assert stop < Decimal("100")
    assert target > Decimal("100")
