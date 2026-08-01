from __future__ import annotations

from backend.services.settings_service import get_or_create_settings

async def test_alert_api_returns_conflict_when_active_cap_is_reached(
    authenticated_client,
    db_session,
    test_user,
):
    settings = await get_or_create_settings(db_session, test_user)
    settings.max_active_alerts = 1
    await db_session.flush()

    first = await authenticated_client.post(
        "/api/alerts",
        json={"ticker": "AAPL", "condition": "above", "target_price": 200, "auto_analyze": False},
    )
    second = await authenticated_client.post(
        "/api/alerts",
        json={"ticker": "MSFT", "condition": "below", "target_price": 300, "auto_analyze": False},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "active alert limit (1)" in second.json()["detail"]
