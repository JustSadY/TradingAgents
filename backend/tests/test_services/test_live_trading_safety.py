from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest

async def test_live_alpaca_executor_rejects_before_constructing_an_http_client(monkeypatch):
    """The executor boundary must be safe even without the orchestrator."""
    from backend.services.execution import alpaca

    monkeypatch.setattr(alpaca, "is_live_trading_enabled", lambda: False)

    def unexpected_http_client(*_args, **_kwargs):
        raise AssertionError("disabled live trading must not construct an HTTP client")

    monkeypatch.setattr(alpaca.httpx, "AsyncClient", unexpected_http_client)
    trader = alpaca.AlpacaTrader(db=object(), mode="live")

    result = await trader.place_order(
        OrderRequest(
            ticker="AAPL",
            action="BUY",
            quantity=Decimal("1"),
            reference_price=Decimal("100"),
        )
    )

    assert result.status == "REJECTED"
    assert "disabled" in result.message.lower()

async def test_orchestrator_skips_live_order_when_server_flag_is_disabled(monkeypatch):
    from backend.repositories import system_settings as system_settings_repo
    from backend.services import trading_orchestrator

    async def get_live_alpaca_settings(_db):
        return SimpleNamespace(trading_mode="live", active_broker="alpaca")

    def unexpected_trader(**_kwargs):
        raise AssertionError("disabled live trading must not create an executor")

    monkeypatch.setattr(system_settings_repo, "get_system_settings", get_live_alpaca_settings)
    monkeypatch.setattr(trading_orchestrator, "is_live_trading_enabled", lambda: False)
    monkeypatch.setattr(trading_orchestrator, "get_trader", unexpected_trader)

    result = await trading_orchestrator.place_signal_order(
        object(),
        ticker="AAPL",
        row=SimpleNamespace(
            signal="Buy",
            chart_annotations={"portfolio_decision": {"rating": "Buy", "position_size_pct": 5}},
            final_decision="",
        ),
        settings=SimpleNamespace(quality_gate_enabled=False),
        user=SimpleNamespace(is_owner=True),
    )

    assert result is None

def test_system_settings_reject_live_mode_while_feature_is_disabled(monkeypatch):
    from backend.services import system_settings_service

    monkeypatch.setattr(system_settings_service, "is_live_trading_enabled", lambda: False)

    with pytest.raises(system_settings_service.InvalidTradingConfiguration, match="disabled"):
        system_settings_service.validate_trading_configuration("live", "alpaca")

def test_metadata_filters_live_options_without_server_opt_in(monkeypatch):
    from backend.core import catalog

    monkeypatch.setattr(catalog, "is_live_trading_enabled", lambda: False)

    owner_modes, owner_brokers = catalog.trading_options_for_user(SimpleNamespace(is_owner=True))
    admin_modes, admin_brokers = catalog.trading_options_for_user(SimpleNamespace(is_owner=False))

    assert [choice["value"] for choice in owner_modes] == ["simulation"]
    assert owner_brokers[-1] == {"value": "alpaca", "label": "Alpaca (Paper)"}
    assert [choice["value"] for choice in admin_modes] == ["simulation"]
    assert [choice["value"] for choice in admin_brokers] == ["simulation"]
