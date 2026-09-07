from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderResult


class _Db:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


class _AlpacaTrader:
    async def get_account_snapshot(self):
        return {
            "cash": 10_000.0,
            "equity": 10_000.0,
            "portfolio_value": 10_000.0,
            "buying_power": 10_000.0,
            "trading_blocked": False,
            "account_blocked": False,
        }

    async def get_positions(self):
        return {}

    async def get_current_price(self, _ticker):
        return 100.0

    async def place_order(self, request):
        return OrderResult(
            order_id="alpaca-order-1",
            status="FILLED",
            filled_price=Decimal("100"),
            filled_quantity=request.quantity,
            external_submission=True,
        )


@pytest.mark.asyncio
async def test_broker_audit_persistence_failure_returns_reconciliation_required(monkeypatch):
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    db = _Db()
    trader = _AlpacaTrader()
    portfolio = SimpleNamespace(
        id=91,
        initial_capital=Decimal("10000"),
        cash_available=Decimal("10000"),
        current_balance=Decimal("10000"),
    )

    async def system_settings(_db):
        return SimpleNamespace(trading_mode="live", active_broker="alpaca")

    async def audit_portfolio(_db, *, user, mode, account):
        assert user.id == 7
        assert mode == "live"
        assert account["equity"] == 10_000.0
        return portfolio

    async def risk_caps(_db, **kwargs):
        return kwargs["quantity"]

    async def broken_audit(*_args, **_kwargs):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(system_settings_repo, "get_system_settings", system_settings)
    monkeypatch.setattr(trading_orchestrator, "is_live_trading_enabled", lambda: True)
    monkeypatch.setattr(trading_orchestrator, "get_trader", lambda **_kwargs: trader)
    monkeypatch.setattr(trading_orchestrator, "_get_or_create_broker_audit_portfolio", audit_portfolio)
    monkeypatch.setattr(trading_orchestrator, "_apply_portfolio_risk_caps", risk_caps)
    monkeypatch.setattr(trading_orchestrator, "_persist_broker_order", broken_audit)

    result = await trading_orchestrator.place_signal_order(
        db,
        ticker="NVDA",
        row=SimpleNamespace(
            id=123,
            signal="Buy",
            analysis_mode="live",
            portfolio_decision_json={
                "rating": "Buy",
                "position_size_pct": 5.0,
                "suggested_capital": 500.0,
                "stop_loss": 95.0,
                "take_profit_price": 110.0,
            },
            final_decision="Open a measured long.",
        ),
        settings=SimpleNamespace(
            quality_gate_enabled=False,
            allow_short_selling=False,
            drawdown_breaker_enabled=False,
            max_risk_per_trade_pct=2.0,
            max_position_size_pct=10.0,
            max_concentration_pct=25.0,
            max_gross_exposure=3.0,
            correlation_risk_enabled=False,
        ),
        user=SimpleNamespace(id=7, is_owner=True),
        include_skip_result=True,
    )

    assert result is not None
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_audit_persist_failed"
    assert result.external_submission is True
    assert "Reconcile the Alpaca account" in result.message
    assert db.rollbacks == 1
