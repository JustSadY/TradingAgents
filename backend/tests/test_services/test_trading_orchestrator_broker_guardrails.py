from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_alpaca_open_short_requires_broker_shorting_permission(monkeypatch):
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    class FakeTrader:
        async def get_account_snapshot(self):
            return {
                "cash": 10_000.0,
                "buying_power": 10_000.0,
                "equity": 10_000.0,
                "portfolio_value": 10_000.0,
                "trading_blocked": False,
                "account_blocked": False,
                "shorting_enabled": False,
            }

        async def get_positions(self):
            return {}

        async def get_current_price(self, _ticker):
            pytest.fail("broker-disabled new short must stop before price I/O")

        async def place_order(self, _request):
            pytest.fail("broker-disabled new short must never be submitted")

    async def fake_system_settings(_db):
        return SimpleNamespace(trading_mode="simulation", active_broker="alpaca")

    async def fake_audit_portfolio(_db, *, user, mode, account):
        return SimpleNamespace(
            id=91,
            initial_capital=Decimal("10000"),
            cash_available=Decimal("10000"),
            current_balance=Decimal("10000"),
        )

    monkeypatch.setattr(system_settings_repo, "get_system_settings", fake_system_settings)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: FakeTrader())
    monkeypatch.setattr(trading_orchestrator, "_get_or_create_broker_audit_portfolio", fake_audit_portfolio)

    row = SimpleNamespace(
        id=501,
        analysis_mode="live",
        strategy_update_status="",
        signal="Sell",
        portfolio_decision_json={
            "rating": "Sell",
            "position_size_pct": 5,
            "suggested_capital": 500,
        },
        quality=None,
        final_decision="Canonical PM short decision",
    )
    settings = SimpleNamespace(
        allow_short_selling=True,
        quality_gate_enabled=False,
        drawdown_breaker_enabled=False,
    )
    owner = SimpleNamespace(id=1, is_owner=True)

    result = await trading_orchestrator.place_signal_order(
        object(),
        ticker="NVDA",
        row=row,
        settings=settings,
        user=owner,
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "SKIPPED"
    assert result.reason_code == "broker_shorting_disabled"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_price", [float("nan"), float("inf"), float("-inf"), "not-a-price"])
async def test_auto_execution_rejects_non_finite_or_invalid_price(monkeypatch, bad_price):
    from backend.repositories import portfolio as portfolio_repo
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    class FakeTrader:
        async def get_current_price(self, _ticker):
            return bad_price

        async def place_order(self, _request):
            pytest.fail("invalid market price must never reach order submission")

    async def fake_system_settings(_db):
        return SimpleNamespace(trading_mode="simulation", active_broker="simulation")

    async def fake_portfolio(_db, user=None):
        return SimpleNamespace(
            id=92,
            initial_capital=Decimal("10000"),
            cash_available=Decimal("10000"),
            current_balance=Decimal("10000"),
        )

    async def fake_holding(_db, _portfolio_id, _ticker):
        return None

    monkeypatch.setattr(system_settings_repo, "get_system_settings", fake_system_settings)
    monkeypatch.setattr(portfolio_repo, "get_holding", fake_holding)
    monkeypatch.setattr(trading_orchestrator, "get_or_create_sim_portfolio", fake_portfolio)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: FakeTrader())

    row = SimpleNamespace(
        id=502,
        analysis_mode="live",
        strategy_update_status="",
        signal="Buy",
        portfolio_decision_json={
            "rating": "Buy",
            "position_size_pct": 5,
            "suggested_capital": 500,
        },
        quality=None,
        final_decision="Canonical PM long decision",
    )
    settings = SimpleNamespace(
        allow_short_selling=False,
        quality_gate_enabled=False,
        drawdown_breaker_enabled=False,
    )

    result = await trading_orchestrator.place_signal_order(
        object(),
        ticker="NVDA",
        row=row,
        settings=settings,
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "SKIPPED"
    assert result.reason_code == "price_unavailable"
