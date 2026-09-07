from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest


def _manual_request() -> OrderRequest:
    return OrderRequest(
        ticker="NVDA",
        action="BUY",
        quantity=Decimal("1"),
        reference_price=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_manual_submit_uncertainty_keeps_a_client_reference(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        client_order_id = None

        def submit_order(self, broker_request):
            self.client_order_id = broker_request.client_order_id
            raise TimeoutError("submit response lost")

        def get_order_by_client_id(self, client_order_id):
            assert client_order_id == self.client_order_id
            raise TimeoutError("reconciliation lookup unavailable")

    trading = Trading()
    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return trading, object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_manual_request())

    assert trading.client_order_id is not None
    assert trading.client_order_id.startswith("ta-manual-")
    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.order_id == f"client:{trading.client_order_id}"
    assert result.external_submission is True


@pytest.mark.asyncio
async def test_cancel_resolves_a_stored_client_reference_before_broker_cancel(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        resolved = None
        canceled = None

        def get_order_by_client_id(self, client_order_id):
            self.resolved = client_order_id
            return SimpleNamespace(id="alpaca-real-uuid")

        def cancel_order_by_id(self, order_id):
            self.canceled = order_id

    trading = Trading()
    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return trading, object()

    monkeypatch.setattr(trader, "_clients", clients)

    canceled = await trader.cancel_order("client:ta-manual-123")

    assert canceled is True
    assert trading.resolved == "ta-manual-123"
    assert trading.canceled == "alpaca-real-uuid"
