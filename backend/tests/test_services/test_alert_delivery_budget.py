from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import alert_service


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
