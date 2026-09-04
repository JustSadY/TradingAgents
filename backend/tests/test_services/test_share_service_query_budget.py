from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services import share_service


async def test_shared_report_create_does_not_refresh_after_flush(monkeypatch) -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    share = SimpleNamespace(
        id=12,
        user_id=7,
        analysis_id=99,
        token="token",
        expires_at=now + timedelta(hours=48),
        created_at=now,
        revoked_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock())

    monkeypatch.setattr(share_service.repo, "get_shared_report_by_analysis", AsyncMock(return_value=None))
    monkeypatch.setattr(share_service.repo, "create_shared_report", AsyncMock(return_value=share))

    result = await share_service.get_or_create_shared_report(db, 99, 7, now)

    assert result is share
    db.commit.assert_awaited_once()
    db.refresh.assert_not_awaited()


async def test_shared_report_rotate_does_not_refresh_after_commit(monkeypatch) -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    share = SimpleNamespace(
        id=12,
        user_id=7,
        analysis_id=99,
        token="old-token",
        expires_at=now - timedelta(minutes=1),
        created_at=now - timedelta(days=1),
        revoked_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock())

    monkeypatch.setattr(share_service.repo, "get_shared_report_by_analysis", AsyncMock(return_value=share))

    result = await share_service.get_or_create_shared_report(db, 99, 7, now)

    assert result is share
    assert share.token != "old-token"
    assert share.expires_at == now + timedelta(hours=48)
    db.commit.assert_awaited_once()
    db.refresh.assert_not_awaited()
