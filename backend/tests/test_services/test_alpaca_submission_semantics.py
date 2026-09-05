from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.services.execution.base import OrderRequest


def _request(**overrides):
    values = {
        "ticker": "NVDA",
        "action": "BUY",
        "quantity": Decimal("1"),
        "reference_price": Decimal("100"),
    }
    values.update(overrides)
    return OrderRequest(**values)


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request", "reason_code"),
    [
        (_request(action="HOLD"), "invalid_action"),
        (_request(quantity=Decimal("NaN")), "invalid_quantity"),
        (_request(quantity=Decimal("Infinity")), "invalid_quantity"),
        (_request(quantity=Decimal("0")), "invalid_quantity"),
    ],
)
async def test_invalid_alpaca_order_input_never_reaches_broker(monkeypatch, request, reason_code):
    from backend.services.execution.alpaca import AlpacaTrader

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        pytest.fail("invalid local input must be rejected before broker client creation")

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(request)

    assert result.status == "REJECTED"
    assert result.reason_code == reason_code
    assert result.external_submission is False


@pytest.mark.asyncio
async def test_alpaca_filled_without_fill_details_requires_reconciliation(monkeypatch):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def submit_order(self, _request):
            return SimpleNamespace(
                id="alpaca-missing-fill",
                status="FILLED",
                filled_avg_price=None,
                filled_qty=None,
            )

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    monkeypatch.setattr(trader, "_clients", clients)

    result = await trader.place_order(_request())

    assert result.status == "RECONCILIATION_REQUIRED"
    assert result.reason_code == "broker_fill_details_missing"
    assert result.external_submission is True
