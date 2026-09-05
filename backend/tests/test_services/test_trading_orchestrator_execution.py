from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderResult
from backend.services.trading_orchestrator import _apply_portfolio_risk_caps, _portfolio_decision, place_signal_order


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


def test_chart_annotation_only_decision_is_not_an_execution_source():
    row = SimpleNamespace(
        portfolio_decision_json=None,
        chart_annotations={"portfolio_decision": {"rating": "Buy", "position_size_pct": 25.0}},
    )

    assert _portfolio_decision(row) == {}


async def test_historical_or_time_travel_result_can_never_place_an_order():
    result = await place_signal_order(
        object(),
        ticker="NVDA",
        row=SimpleNamespace(
            signal="Buy",
            analysis_mode="historical",
            portfolio_decision_json={"rating": "Buy", "position_size_pct": 10.0},
            final_decision="",
        ),
        settings=_opening_settings(),
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "SKIPPED"
    assert result.reason_code == "non_live_analysis"


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
        row=SimpleNamespace(
            signal=signal,
            portfolio_decision_json={"rating": signal},
            final_decision="",
        ),
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


async def test_sell_with_positive_target_opens_short_when_short_selling_is_enabled(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    portfolio = SimpleNamespace(
        id=42,
        initial_capital=Decimal("10000"),
        current_balance=Decimal("10000"),
        cash_available=Decimal("10000"),
    )
    trader = _FakeTrader()

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return None

    async def _get_portfolio(_db, user=None):
        return portfolio

    async def _allocation_snapshot(_db, *, portfolio):
        return {"total_value": 10_000.0, "holdings": []}

    async def _risk_caps(_db, **kwargs):
        return kwargs["quantity"]

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)
    monkeypatch.setattr(trading_orchestrator, "_allocation_snapshot", _allocation_snapshot)
    monkeypatch.setattr(trading_orchestrator, "_apply_portfolio_risk_caps", _risk_caps)

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Sell",
            analysis_mode="live",
            portfolio_decision_json={
                "rating": "Sell",
                "position_size_pct": 5.0,
                "suggested_capital": 500.0,
                "stop_loss": 110.0,
                "take_profit_price": 90.0,
                "recommended_leverage": 1.0,
            },
            final_decision="Open a measured short.",
        ),
        settings=_opening_settings(allow_short_selling=True),
    )

    assert result is not None
    assert trader.request is not None
    assert trader.request.action == "SELL"
    assert trader.request.allow_short is True
    assert trader.request.quantity > 0
    assert trader.request.stop_loss == Decimal("110.0")
    assert trader.request.take_profit == Decimal("90.0")


async def test_sell_zero_target_does_not_open_short_from_flat(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    portfolio = SimpleNamespace(
        id=42,
        initial_capital=Decimal("10000"),
        current_balance=Decimal("10000"),
        cash_available=Decimal("10000"),
    )
    trader = _FakeTrader()

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return None

    async def _get_portfolio(_db, user=None):
        return portfolio

    async def _allocation_snapshot(_db, *, portfolio):
        return {"total_value": 10_000.0, "holdings": []}

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)
    monkeypatch.setattr(trading_orchestrator, "_allocation_snapshot", _allocation_snapshot)

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Sell",
            analysis_mode="live",
            portfolio_decision_json={"rating": "Sell", "position_size_pct": 0.0},
            final_decision="Stay flat.",
        ),
        settings=_opening_settings(allow_short_selling=True),
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "SKIPPED"
    assert result.reason_code == "target_allocation_met"
    assert trader.request is None


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
    assert received_kwargs == {
        "portfolio_id": 42,
        "read_only": True,
        "release_before_price_io": True,
    }


async def test_portfolio_risk_snapshot_failure_fails_closed_for_new_exposure(monkeypatch):
    from backend.services import mock_trading_service

    async def _snapshot(_db, **_kwargs):
        raise RuntimeError("market-data outage")

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

    assert quantity == 0.0


def _opening_settings(**overrides):
    values = {
        "quality_gate_enabled": False,
        "allow_short_selling": False,
        "drawdown_breaker_enabled": False,
        "max_risk_per_trade_pct": 2.0,
        "max_position_size_pct": 10.0,
        "max_concentration_pct": 25.0,
        "max_gross_exposure": 3.0,
        "correlation_risk_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_drawdown_snapshot_error_blocks_a_new_position(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import mock_trading_service, trading_orchestrator

    portfolio = SimpleNamespace(id=42, initial_capital=Decimal("10000"), cash_available=Decimal("9000"))

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return None

    async def _get_portfolio(_db, user=None):
        return portfolio

    async def _snapshot(_db, **_kwargs):
        raise RuntimeError("market-data outage")

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", _snapshot)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: pytest.fail("must not request a trade"))

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Buy",
            portfolio_decision_json={"rating": "Buy", "position_size_pct": 5},
            final_decision="",
        ),
        settings=_opening_settings(drawdown_breaker_enabled=True, max_portfolio_drawdown_pct=20.0),
    )

    assert result is None


async def test_drawdown_snapshot_error_does_not_block_a_safe_exit(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import mock_trading_service, trading_orchestrator

    portfolio = SimpleNamespace(id=42, initial_capital=Decimal("10000"), cash_available=Decimal("9000"))
    holding = SimpleNamespace(side="long", quantity=Decimal("7.25"))
    trader = _FakeTrader()
    snapshot_calls = 0

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return holding

    async def _get_portfolio(_db, user=None):
        return portfolio

    async def _snapshot(_db, **_kwargs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        raise RuntimeError("must not be called for exits")

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", _snapshot)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Sell",
            portfolio_decision_json={"rating": "Sell"},
            final_decision="",
        ),
        settings=_opening_settings(drawdown_breaker_enabled=True, max_portfolio_drawdown_pct=20.0),
    )

    assert result is not None
    assert trader.request.quantity == Decimal("7.25")
    assert snapshot_calls == 0


async def test_zero_cash_never_falls_back_to_initial_capital_for_position_sizing(monkeypatch):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    portfolio = SimpleNamespace(id=42, initial_capital=Decimal("10000"), cash_available=Decimal("0"))
    trader = _FakeTrader()

    async def _get_system_settings(_db):
        return None

    async def _get_holding(_db, _portfolio_id, _ticker):
        return None

    async def _get_portfolio(_db, user=None):
        return portfolio

    monkeypatch.setattr(system_settings_repo, "get_system_settings", _get_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", _get_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", _get_portfolio)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)

    result = await place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Buy",
            portfolio_decision_json={"rating": "Buy", "position_size_pct": 5},
            final_decision="",
        ),
        settings=_opening_settings(),
    )

    assert result is None
    assert trader.request is None
