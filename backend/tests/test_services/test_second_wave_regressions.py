from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services.analysis.emitter import AnalysisEmitter
from backend.services.analysis.orchestrator import _emit_system_status, _heartbeat_monitor
from backend.services.trade_journal_service import _realized_cost_basis, _realized_pnl_pct

class _AsyncSessionContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def commit(self):
        return None

async def test_portfolio_assistant_uses_execute_order_result_keys(monkeypatch):
    from backend.core import database
    from backend.services import mock_trading_service, portfolio_assistant_service

    async def fake_execute_order(*_args, **_kwargs):
        return {"quantity": 2.0, "price": 12.5}

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(mock_trading_service, "execute_order", fake_execute_order)

    message = await portfolio_assistant_service._tool_place_paper_order(
        SimpleNamespace(), {"trading"}, "aapl", "buy", 2.0
    )

    assert message == "Order placed: BUY 2.0000 shares of AAPL @ $12.50. Total: $25.00."

class _RecordingAnalysisEmitter(AnalysisEmitter):
    def __init__(self):
        super().__init__("task-1")
        self.events: list[dict] = []

    async def emit(self, event: dict):
        self.events.append(event)

async def test_orchestrator_system_status_keeps_message_out_of_agent_field():
    emitter = _RecordingAnalysisEmitter()

    await _emit_system_status(emitter, "Initializing")

    assert emitter.events == [
        {
            "type": "status",
            "agent": "system",
            "status": "starting",
            "message": "Initializing",
        }
    ]

class _HeartbeatEmitter:
    task_id = "task-1"

    def __init__(self):
        self.events: list[dict] = []
        self.progress: list[tuple[str, str, str]] = []

    async def emit(self, event: dict):
        self.events.append(event)

    async def emit_progress(self, label: str, stage: str, node: str):
        self.progress.append((label, stage, node))

async def test_heartbeat_continues_after_a_stall_without_repeating_the_warning():
    emitter = _HeartbeatEmitter()
    clock_values = iter((20.0, 40.0))
    sleep_calls = 0

    async def fake_sleep(_seconds: float):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _heartbeat_monitor(
            emitter,
            last_event_at=lambda: 0.0,
            stall_timeout=10.0,
            sleep=fake_sleep,
            now=lambda: next(clock_values),
        )

    assert emitter.events == [
        {
            "type": "stall_warning",
            "seconds_since_last_event": 20.0,
            "threshold": 10.0,
        }
    ]
    assert emitter.progress == [
        ("heartbeat", "stalled", "system"),
        ("heartbeat", "stalled", "system"),
    ]

async def test_performance_compares_spy_over_the_portfolio_lifetime(monkeypatch):
    from backend.services import market_data_service, mock_trading_service

    portfolio = SimpleNamespace(id=42, created_at=datetime(2024, 5, 10, tzinfo=UTC))
    snapshot_calls: list[dict] = []
    benchmark_calls: list[dict] = []

    async def fake_portfolio(*_args, **_kwargs):
        return portfolio

    async def fake_snapshot(_db, **kwargs):
        snapshot_calls.append(kwargs)
        return {"total_pnl_pct": 5.0}

    async def fake_benchmark(benchmark="SPY", period="1y", *, start_date=None, end_date=None):
        benchmark_calls.append(
            {"benchmark": benchmark, "period": period, "start_date": start_date, "end_date": end_date}
        )
        return 3.25

    monkeypatch.setattr(mock_trading_service, "get_or_create_sim_portfolio", fake_portfolio)
    monkeypatch.setattr(mock_trading_service, "get_portfolio_with_live_prices", fake_snapshot)
    monkeypatch.setattr(market_data_service, "get_benchmark_return", fake_benchmark)

    user = SimpleNamespace(id=1)
    result = await mock_trading_service.get_performance(object(), user=user)

    assert snapshot_calls == [{"user": user, "portfolio_id": 42}]
    assert benchmark_calls == [{"benchmark": "SPY", "period": "1y", "start_date": "2024-05-10", "end_date": None}]
    assert result["alpha_pct"] == 1.75

async def test_explicit_benchmark_dates_are_forwarded_to_the_market_provider(monkeypatch):
    from backend.services import market_data_service

    received: list[dict] = []

    class _Ticker:
        def history(self, **kwargs):
            received.append(kwargs)
            return pd.DataFrame({"Close": [100.0, 110.0]})

    async def run_synchronously(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(market_data_service.yf, "Ticker", lambda _ticker: _Ticker())
    monkeypatch.setattr(market_data_service.asyncio, "to_thread", run_synchronously)

    result = await market_data_service.get_benchmark_return("SPY", start_date="2024-05-10", end_date="2024-05-20")

    assert received == [{"start": "2024-05-10", "end": "2024-05-20"}]
    assert result == 10.0

@pytest.mark.parametrize(
    ("side", "total_value", "commission", "pnl", "expected_cost_basis", "expected_pct"),
    [
        ("long", "1200", "1.2", "198.8", "1000", 19.88),
        ("short", "800", "0.8", "199.2", "1000", 19.92),
    ],
)
def test_trade_journal_uses_entry_cost_basis_for_long_and_short_returns(
    side,
    total_value,
    commission,
    pnl,
    expected_cost_basis,
    expected_pct,
):
    order = SimpleNamespace(
        side=side,
        total_value=Decimal(total_value),
        commission=Decimal(commission),
        realized_pnl=Decimal(pnl),
        quantity_filled=Decimal("100"),
        price_per_share=Decimal(total_value) / Decimal("100"),
    )

    assert _realized_cost_basis(order) == Decimal(expected_cost_basis)
    assert _realized_pnl_pct(order) == pytest.approx(expected_pct)

@pytest.mark.parametrize(
    ("side", "total_value", "exit_commission", "entry_commission", "pnl", "expected_cost", "expected_pct"),
    [
        ("long", "1200", "1.2", "1", "197.8", "1001", 197.8 / 1001 * 100),
        ("short", "800", "0.8", "1", "198.2", "1001", 198.2 / 1001 * 100),
    ],
)
def test_trade_journal_uses_all_in_entry_fee_for_current_closing_orders(
    side,
    total_value,
    exit_commission,
    entry_commission,
    pnl,
    expected_cost,
    expected_pct,
):
    order = SimpleNamespace(
        side=side,
        total_value=Decimal(total_value),
        commission=Decimal(exit_commission),
        entry_commission=Decimal(entry_commission),
        realized_pnl=Decimal(pnl),
        quantity_filled=Decimal("100"),
        price_per_share=Decimal(total_value) / Decimal("100"),
    )

    assert _realized_cost_basis(order) == Decimal(expected_cost)
    assert _realized_pnl_pct(order) == pytest.approx(expected_pct)

async def test_cron_uses_the_orchestrator_signal_mapping(monkeypatch):
    from backend.services import cron_service

    placed: list[dict] = []
    commits = 0

    class _Db:
        async def commit(self):
            nonlocal commits
            commits += 1

    async def fake_place_order(db, **kwargs):
        placed.append({"db": db, **kwargs})

    monkeypatch.setattr(cron_service, "is_actionable", lambda signal: signal == "NewActionableSignal")
    monkeypatch.setattr(cron_service, "place_signal_order", fake_place_order)
    row = SimpleNamespace(signal="NewActionableSignal")

    was_placed = await cron_service._place_actionable_signal_order(
        _Db(),
        ticker="AAPL",
        row=row,
        settings=SimpleNamespace(auto_execute_signals=True),
        user=SimpleNamespace(id=1),
    )

    assert was_placed is True
    assert len(placed) == 1
    assert commits == 1
