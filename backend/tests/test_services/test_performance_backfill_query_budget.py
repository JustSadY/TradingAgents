from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import performance_service as service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


async def test_backfill_batches_owner_settings_and_users(monkeypatch) -> None:
    db = _TrackingDB()
    rows = [
        SimpleNamespace(user_id=7, ticker="AAPL", trade_date="2026-08-01"),
        SimpleNamespace(user_id=7, ticker="MSFT", trade_date="2026-08-01"),
        SimpleNamespace(user_id=8, ticker="NVDA", trade_date="2026-08-01"),
    ]
    list_candidates = AsyncMock(return_value=rows)
    settings_map = AsyncMock(return_value={7: SimpleNamespace(), 8: SimpleNamespace()})
    users_map = AsyncMock(return_value={7: SimpleNamespace(id=7), 8: SimpleNamespace(id=8)})

    async def calculate(*_args, **_kwargs):
        assert db.commits == 1
        return None, None, None

    monkeypatch.setattr(service, "list_return_backfill_candidates", list_candidates)
    monkeypatch.setattr(service, "get_app_settings_map", settings_map)
    monkeypatch.setattr(service, "get_users_by_ids", users_map)
    monkeypatch.setattr(service, "calculate_returns", calculate)
    monkeypatch.setattr(service, "resolve_benchmark", lambda _ticker, _config: "SPY")
    monkeypatch.setattr("backend.trading_agents.dataflows.config.get_config", lambda: {})

    updated = await service.backfill_returns(db)

    assert updated == 0
    assert db.commits == 1
    settings_map.assert_awaited_once_with(db, {7, 8})
    users_map.assert_awaited_once_with(db, {7, 8})


async def test_backfill_return_fetches_are_bounded(monkeypatch) -> None:
    rows = [
        SimpleNamespace(user_id=None, ticker=f"T{index}", trade_date="2026-08-01")
        for index in range(10)
    ]
    release = asyncio.Event()
    active = 0
    max_active = 0
    db = _TrackingDB()

    async def fake_calculate(*_args, **_kwargs):
        nonlocal active, max_active
        assert db.commits == 1
        active += 1
        max_active = max(max_active, active)
        if active >= service._BACKFILL_RETURN_CONCURRENCY:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        active -= 1
        return None, None, None

    monkeypatch.setattr(service, "list_return_backfill_candidates", AsyncMock(return_value=rows))
    monkeypatch.setattr(service, "get_app_settings_map", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "get_users_by_ids", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "calculate_returns", fake_calculate)
    monkeypatch.setattr(service, "resolve_benchmark", lambda _ticker, _config: "SPY")
    monkeypatch.setattr("backend.trading_agents.dataflows.config.get_config", lambda: {})

    updated = await service.backfill_returns(db)

    assert updated == 0
    assert db.commits == 1
    assert max_active == service._BACKFILL_RETURN_CONCURRENCY
