from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderResult
from backend.services.trading_orchestrator import _apply_portfolio_risk_caps, place_signal_order


class _FakeTrader:
    def __init__(self):
        self.request = None

    async def get_current_price(self, _ticker: str):
        return 100.0

    async def place_order(self, request):
        self.request = request
        return OrderResult(
            order_id="test",
            status="FILLED",
            filled_price=Decimal("100"),
            filled_quantity=request.quantity,
        )


@pytest.mark.parametrize(
    ("signal", "holding_side", "expected_action"),
    [
        ("Sell", "long", "SELL"),
        ("Buy", "short", "BUY"),
    ],
)
async def test_signal_exit_closes_the_entire_held_position_not_a_new_risk_sized_amount(
    monkeypatch,
    signal,
    holding_side,
    expected_action,
):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    portfolio = SimpleNamespace(
        id=42,
        initial_capital=Decimal("10000"),
        cash_available=Decimal("9000"),
    )
    holding = SimpleNamespace(side=holding_side, quantity=Decimal("7.25"))
    trader = _FakeTrader()

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return holding

    async def _get_portfolio(_db, user=None):
        return portfolio

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(signal=signal, chart_annotations=None, final_decision=""),
        settings=SimpleNamespace(
            quality_gate_enabled=False,
            allow_short_selling=False,
            drawdown_breaker_enabled=False,
        ),
    )

    assert result is not None
    assert trader.request is not None
    assert trader.request.action == expected_action
    assert trader.request.quantity == Decimal("7.25")
    assert trader.request.leverage == 1.0
    assert trader.request.stop_loss is None
    assert trader.request.take_profit is None


async def test_portfolio_risk_snapshot_is_read_only(monkeypatch):
    from backend.services import mock_trading_service

    received_kwargs = {}

    async def _snapshot(_db, **kwargs):
        received_kwargs.update(kwargs)
        return {"total_value": 10_000.0, "holdings": []}

    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", _snapshot)

    quantity = await _apply_portfolio_risk_caps(
        object(),
        portfolio=SimpleNamespace(id=42),
        ticker="AAPL",
        price=100.0,
        quantity=10.0,
        settings=SimpleNamespace(
            correlation_risk_enabled=False,
            max_concentration_pct=25.0,
            max_gross_exposure=3.0,
        ),
    )

    assert quantity == 10.0
    assert received_kwargs == {"portfolio_id": 42, "read_only": True}
