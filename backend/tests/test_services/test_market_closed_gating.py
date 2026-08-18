"""Automated selling and scheduled scans stop while the exchange is shut."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from backend.services import trading_orchestrator
from backend.services.execution.base import OrderResult

# US Independence Day 2026 falls on a Saturday; the NYSE observes it on the 3rd.
NYSE_HOLIDAY = "2026-07-03"
NYSE_SESSION = "2026-07-06"


def _settings():
    return SimpleNamespace(
        quality_gate_enabled=False,
        allow_short_selling=False,
        drawdown_breaker_enabled=False,
        max_risk_per_trade_pct=2.0,
        max_position_size_pct=10.0,
        max_concentration_pct=25.0,
        max_gross_exposure=3.0,
        correlation_risk_enabled=False,
        auto_execute_signals=True,
    )


def _row(trade_date: str | None, *, asset_type: str = "stock"):
    return SimpleNamespace(
        id=19,
        signal="Buy",
        trade_date=trade_date,
        asset_type=asset_type,
        analysis_mode="live",
        strategy_update_status="",
        portfolio_decision_json={
            "rating": "Buy",
            "position_size_pct": 5,
            "entry_price": 100,
            "suggested_capital": 300,
        },
        final_decision="Portfolio Manager: Buy.",
    )


async def _place(monkeypatch, *, ticker: str, row) -> OrderResult | None:
    """Drive place_signal_order with every downstream dependency stubbed out.

    Everything past the calendar gate is faked so a result other than
    ``market_closed`` proves the gate let the order through.
    """
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import mock_trading_service

    class FakeTrader:
        async def get_current_price(self, _ticker):
            return 100.0

        async def place_order(self, request):
            return OrderResult(
                order_id="auto-1",
                status="FILLED",
                filled_price=Decimal("100"),
                filled_quantity=request.quantity,
            )

    async def fake_system_settings(_db):
        return None

    async def fake_holding(_db, _portfolio_id, _ticker):
        return None

    async def fake_portfolio(_db, user=None):
        return SimpleNamespace(id=44, initial_capital=Decimal("10000"), cash_available=Decimal("10000"))

    async def fake_snapshot(_db, **_kwargs):
        return {"total_value": 10_000.0, "holdings": []}

    monkeypatch.setattr(system_settings_repo, "get_system_settings", fake_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", fake_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", fake_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", fake_snapshot)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: FakeTrader())

    return await trading_orchestrator.place_signal_order(
        object(), ticker=ticker, row=row, settings=_settings(), include_skip_result=True
    )


class TestAutoOrderExchangeGate:
    async def test_a_holiday_order_is_skipped_before_any_broker_work(self, monkeypatch):
        result = await _place(monkeypatch, ticker="AAPL", row=_row(NYSE_HOLIDAY))

        assert result is not None
        assert result.status == "SKIPPED"
        assert result.reason_code == "market_closed"
        assert "XNYS" in result.message

    async def test_the_same_order_goes_through_on_a_session_day(self, monkeypatch):
        result = await _place(monkeypatch, ticker="AAPL", row=_row(NYSE_SESSION))

        assert result is not None and result.status == "FILLED"

    async def test_crypto_is_never_gated_by_an_equity_holiday(self, monkeypatch):
        result = await _place(
            monkeypatch,
            ticker="BTC-USD",
            row=_row(NYSE_HOLIDAY, asset_type="crypto"),
        )

        assert result is not None and result.status == "FILLED"

    async def test_a_row_without_a_trade_date_is_not_gated(self, monkeypatch):
        result = await _place(monkeypatch, ticker="AAPL", row=_row(None))

        assert result is not None and result.status == "FILLED"

    def test_the_session_date_is_read_from_the_row(self):
        assert trading_orchestrator._trade_date(_row(NYSE_SESSION)) == date(2026, 7, 6)
        assert trading_orchestrator._trade_date(_row("not-a-date")) is None
        assert trading_orchestrator._trade_date(SimpleNamespace()) is None


async def _auto_closes_for(db, monkeypatch, *, ticker: str, trading_day: bool) -> list[dict]:
    """Run one position-monitor pass over a single stop-loss-breaching holding."""
    from backend.models.portfolio import Holding, Portfolio
    from backend.services import mock_trading_service

    portfolio = Portfolio(
        user_id=None,
        mode="simulation",
        broker="simulation",
        initial_capital=Decimal("10000"),
        current_balance=Decimal("9000"),
        cash_available=Decimal("9000"),
    )
    db.add(portfolio)
    await db.flush()
    db.add(
        Holding(
            portfolio_id=portfolio.id,
            ticker=ticker,
            quantity=Decimal("10"),
            avg_buy_price=Decimal("100"),
            current_price=Decimal("100"),
            side="long",
            stop_loss=Decimal("95"),
        )
    )
    await db.flush()

    # A quote well under the stop: only the calendar gate can hold the sell back.
    async def fake_prices(_tickers):
        return {ticker: 80.0}

    monkeypatch.setattr(mock_trading_service, "get_live_prices_batch", fake_prices)
    monkeypatch.setattr(mock_trading_service, "is_trading_day", lambda *_a, **_k: trading_day)

    snapshot = await mock_trading_service.get_portfolio_with_live_prices(db, portfolio_id=portfolio.id)
    return snapshot["auto_closes"]


class TestPositionMonitorExchangeGate:
    async def test_a_stop_loss_does_not_fire_on_an_exchange_holiday(self, db, monkeypatch):
        """The vendor still serves the previous close, which looks fresh here."""
        assert await _auto_closes_for(db, monkeypatch, ticker="AAPL", trading_day=False) == []

    async def test_the_same_stop_loss_fires_on_a_session_day(self, db, monkeypatch):
        closes = await _auto_closes_for(db, monkeypatch, ticker="AAPL", trading_day=True)
        assert [entry["reason"] for entry in closes] == ["STOP_LOSS"]

    async def test_crypto_keeps_being_monitored(self):
        from backend.services.market_calendar_service import is_trading_day

        assert is_trading_day(date(2026, 7, 3), ticker="BTC-USD") is True
