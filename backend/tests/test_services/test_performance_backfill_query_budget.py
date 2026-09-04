from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import performance_service as service


async def test_backfill_batches_owner_settings_and_users(monkeypatch) -> None:
    rows = [
        SimpleNamespace(user_id=7, ticker="AAPL", trade_date="2026-08-01"),
        SimpleNamespace(user_id=7, ticker="MSFT", trade_date="2026-08-01"),
        SimpleNamespace(user_id=8, ticker="NVDA", trade_date="2026-08-01"),
    ]
    list_candidates = AsyncMock(return_value=rows)
    settings_map = AsyncMock(return_value={7: SimpleNamespace(), 8: SimpleNamespace()})
    users_map = AsyncMock(return_value={7: SimpleNamespace(id=7), 8: SimpleNamespace(id=8)})
    calculate = AsyncMock(return_value=(None, None, None))

    monkeypatch.setattr(service, "list_return_backfill_candidates", list_candidates)
    monkeypatch.setattr(service, "get_app_settings_map", settings_map)
    monkeypatch.setattr(service, "get_users_by_ids", users_map)
    monkeypatch.setattr(service, "calculate_returns", calculate)
    monkeypatch.setattr(service, "resolve_benchmark", lambda _ticker, _config: "SPY")
    monkeypatch.setattr("backend.trading_agents.dataflows.config.get_config", lambda: {})

    updated = await service.backfill_returns(object())

    assert updated == 0
    settings_map.assert_awaited_once_with(object(), {7, 8})
    users_map.assert_awaited_once_with(object(), {7, 8})
    assert calculate.await_count == 3
