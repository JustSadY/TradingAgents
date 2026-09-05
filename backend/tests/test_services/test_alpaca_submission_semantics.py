from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest


def _request():
    return OrderRequest(
        ticker="NVDA",
        action="BUY",
        quantity=Decimal("1"),
        reference_price=Decimal("100"),
    )


@pytest.mark.asyncio
async def test_alpaca_success_marks_result_as_external_submission(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def submit_order(self, _request):
            return SimpleNamespace(
                id="alpaca-1",
                status="FILLED",
                filled_avg_price="100",
                filled_qty="1",
            )

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_request())

    assert result.status == "FILLED"
    assert result.order_id == "alpaca-1"
    assert result.external_submission is True


@pytest.mark.asyncio
async def test_alpaca_submit_exception_is_reconciliation_required_not_rejected(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def submit_order(self, _request):
            raise TimeoutError("response lost after submit")

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_request())

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_submission_uncertain"
    assert result.external_submission is True
    assert "reconcile" in result.message.lower()
