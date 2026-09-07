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


class _Db:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


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


async def test_outbox_market_summary_releases_transaction_before_external_io(monkeypatch) -> None:
    db = _Db()
    item = SimpleNamespace(status="processing", alert_id=11)
    alert = SimpleNamespace(ticker="AAPL")
    get_item = AsyncMock(return_value=item)
    get_alert = AsyncMock(return_value=alert)

    async def fake_summary(ticker: str) -> str:
        assert ticker == "AAPL"
        assert db.commits == 1
        assert db.rollbacks == 0
        return "summary"

    monkeypatch.setattr(alert_service, "get_outbox_item", get_item)
    monkeypatch.setattr(alert_service, "get_alert_unscoped", get_alert)
    monkeypatch.setattr(alert_service, "_fetch_alert_market_summary", fake_summary)

    result = await alert_service._prepare_outbox_market_summary(db, 5)

    assert result == "summary"
    get_item.assert_awaited_once_with(db, 5)
    get_alert.assert_awaited_once_with(db, 11)
    assert db.commits == 1


async def test_claimed_outbox_delivery_is_bounded(monkeypatch) -> None:
    active = 0
    max_active = 0
    delivered: list[int] = []
    release = asyncio.Event()
    set_context = AsyncMock()

    async def fake_deliver(_db, item_id: int, *, market_summary: str | None = None) -> None:
        nonlocal active, max_active
        assert market_summary == "summary"
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
    monkeypatch.setattr(alert_service, "_prepare_outbox_market_summary", AsyncMock(return_value="summary"))
    monkeypatch.setattr(alert_service, "_deliver_outbox_item", fake_deliver)

    await asyncio.gather(*[alert_service._deliver_claimed_outbox_item(item_id, 7) for item_id in range(8)])

    assert sorted(delivered) == list(range(8))
    assert max_active == 3
    assert set_context.await_count == 8
