from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_blocked"),
    [
        ("ACTIVE", False),
        ("PAPER_ONLY", False),
        ("ACCOUNT_UPDATED", True),
        ("ACTION_REQUIRED", True),
        ("DISABLED", True),
        ("INACTIVE", True),
    ],
)
async def test_alpaca_account_status_fails_closed_when_not_tradeable(monkeypatch, status, expected_blocked):
    from backend.services.execution.alpaca import AlpacaTrader

    class Trading:
        def get_account(self):
            return SimpleNamespace(
                cash="1000",
                buying_power="1000",
                equity="1000",
                portfolio_value="1000",
                status=status,
                trading_blocked=False,
                account_blocked=False,
                trade_suspended_by_user=False,
                shorting_enabled=True,
            )

    trader = AlpacaTrader(db=object(), mode="simulation")

    async def clients():
        return Trading(), object()

    monkeypatch.setattr(trader, "_clients", clients)

    snapshot = await trader.get_account_snapshot()

    assert snapshot["status"] == status
    assert snapshot["trading_blocked"] is expected_blocked
