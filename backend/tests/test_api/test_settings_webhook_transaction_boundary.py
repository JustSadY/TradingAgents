from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.api import settings as settings_api
from backend.schemas.webhook import WebhookTestRequest


class _TrackingDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_webhook_probe_releases_db_before_dns_and_http_io(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _TrackingDB()

    async def fake_permission(*_args, **_kwargs):
        assert db.commits == 0

    async def fake_resolve(url: str):
        assert url == "https://example.com/hook"
        assert db.commits == 1

    async def fake_test(url: str) -> bool:
        assert url == "https://example.com/hook"
        assert db.commits == 1
        return True

    monkeypatch.setattr(settings_api, "enforce_setting_section_permission", fake_permission)
    monkeypatch.setattr(settings_api, "resolve_webhook_target", fake_resolve)
    monkeypatch.setattr(settings_api, "test_webhook_url", fake_test)

    result = await settings_api.test_webhook(
        body=WebhookTestRequest(url="https://example.com/hook"),
        db=db,
        current_user=SimpleNamespace(id=7, is_admin=False),
    )

    assert result == {"ok": True}
    assert db.commits == 1
