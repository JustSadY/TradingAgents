from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.schemas.settings import SettingsUpdate
from backend.services import notification_service, settings_service


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0
        self.flushes = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        self.flushes += 1


@pytest.mark.asyncio
async def test_settings_update_releases_db_before_webhook_dns_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    settings = SimpleNamespace(
        webhook_url=None,
        auto_execute_signals=False,
        active_preset_name=None,
        user_id=7,
    )

    async def fake_resolve(url: str):
        assert url == "https://example.com/hook"
        assert db.commits == 1
        raise RuntimeError("webhook boundary reached")

    monkeypatch.setattr(notification_service, "resolve_webhook_target", fake_resolve)

    with pytest.raises(RuntimeError, match="webhook boundary reached"):
        await settings_service.apply_settings_update(
            db,
            settings,
            SettingsUpdate(webhook_url="https://example.com/hook"),
        )

    assert db.commits == 1
    assert db.flushes == 0
    assert settings.webhook_url is None


@pytest.mark.asyncio
async def test_preset_releases_db_before_webhook_dns_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()
    settings = SimpleNamespace(
        webhook_url=None,
        auto_execute_signals=False,
        active_preset_name=None,
        user_id=7,
    )
    preset = SimpleNamespace(
        name="Webhook preset",
        settings_json='{"webhook_url":"https://example.com/hook"}',
    )

    async def fake_settings(*_args, **_kwargs):
        return settings

    async def fake_resolve(url: str):
        assert url == "https://example.com/hook"
        assert db.commits == 1
        raise RuntimeError("preset boundary reached")

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_settings)
    monkeypatch.setattr(notification_service, "resolve_webhook_target", fake_resolve)

    with pytest.raises(RuntimeError, match="preset boundary reached"):
        await settings_service.apply_preset_to_settings(db, SimpleNamespace(id=7), preset)

    assert db.commits == 1
    assert db.flushes == 0
    assert settings.webhook_url is None
