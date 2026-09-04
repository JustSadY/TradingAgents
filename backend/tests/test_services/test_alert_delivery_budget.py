from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import alert_service


class _SessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args) -> bool:
        return False


async def test_auto_analyze_alert_reuses_one_user_settings_read(monkeypatch) -> None:
    db = object()
    system_settings = object()
    user = SimpleNamespace(id=7)
    settings = SimpleNamespace()
    alert = SimpleNamespace(
        user_id=7,
        ticker="AAPL",
        condition="above",
        target_price=100.0,
        alert_type="price",
        auto_analyze=True,
    )

    get_user = AsyncMock(return_value=user)
    get_settings = AsyncMock(return_value=settings)
    notify = AsyncMock()
    create_result = AsyncMock()
    register_task = AsyncMock()
    dispatch = AsyncMock()

    monkeypatch.setattr(alert_service, "_fetch_alert_market_summary", AsyncMock(return_value=""))
    monkeypatch.setattr(alert_service, "get_user_by_id", get_user)
    monkeypatch.setattr(alert_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr(alert_service, "notify_alert_triggered", notify)
    monkeypatch.setattr("backend.repositories.analysis.create_analysis_result", create_result)
    monkeypatch.setattr("backend.services.analysis_service.register_queued_task", register_task)
    monkeypatch.setattr("backend.services.analysis_queue.dispatch_analysis", dispatch)

    await alert_service._deliver_alert_side_effects(db, alert, system_settings, 101.0)

    get_user.assert_awaited_once_with(db, 7)
    get_settings.assert_awaited_once_with(db, user)
    notify.assert_awaited_once()
    create_result.assert_awaited_once()
    register_task.assert_awaited_once()
    dispatch.assert_awaited_once()


async def test_claimed_outbox_delivery_is_bounded(monkeypatch) -> None:
    active = 0
    max_active = 0
    delivered: list[int] = []
    release = asyncio.Event()
    set_context = AsyncMock()

    async def fake_deliver(_db, item_id: int) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active >= 3:
            release.set()
        await release.wait()
        await asyncio.sleep(0)
        delivered.append(item_id)
        active -= 1

    monkeypatch.setattr(alert_service, "_OUTBOX_SEMAPHORE", asyncio.Semaphore(3))
    monkeypatch.setattr(alert_service, "AsyncSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(alert_service, "set_user_background_context", set_context)
    monkeypatch.setattr(alert_service, "_deliver_outbox_item", fake_deliver)

    await asyncio.gather(*[alert_service._deliver_claimed_outbox_item(item_id, 7) for item_id in range(8)])

    assert sorted(delivered) == list(range(8))
    assert max_active == 3
    assert set_context.await_count == 8
