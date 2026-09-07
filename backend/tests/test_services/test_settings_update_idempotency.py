from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import backend.services.settings_service as settings_service
from backend.schemas.settings import SettingsUpdate
from backend.services.settings_service import apply_preset_to_settings, apply_settings_update


class _Db:
    def __init__(self) -> None:
        self.flushes = 0
        self.commits = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


async def _noop_emit(*_args, **_kwargs) -> None:
    return None


async def test_unchanged_settings_update_skips_write_commit_and_timestamp_change() -> None:
    updated_at = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
    settings = SimpleNamespace(
        output_language="English",
        auto_execute_signals=False,
        active_preset_name="baseline",
        webhook_url=None,
        updated_at=updated_at,
    )
    db = _Db()

    result = await apply_settings_update(
        db,
        settings,
        SettingsUpdate(output_language="English"),
    )

    assert result is settings
    assert settings.updated_at is updated_at
    assert settings.active_preset_name == "baseline"
    assert db.flushes == 0
    assert db.commits == 0


async def test_reapplying_identical_active_preset_is_a_noop(monkeypatch) -> None:
    updated_at = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
    settings = SimpleNamespace(
        user_id=7,
        output_language="English",
        auto_execute_signals=False,
        active_preset_name="baseline",
        webhook_url=None,
        updated_at=updated_at,
    )

    async def fake_get_settings(_db, _user):
        return settings

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_get_settings)
    db = _Db()

    result = await apply_preset_to_settings(
        db,
        SimpleNamespace(id=7),
        SimpleNamespace(name="baseline", settings_json='{"output_language":"English"}'),
    )

    assert result == "baseline"
    assert settings.updated_at is updated_at
    assert db.flushes == 0
    assert db.commits == 0


async def test_marker_only_preset_change_commits_without_runtime_event(monkeypatch) -> None:
    emitted = []
    updated_at = datetime(2026, 9, 4, 8, 0, tzinfo=UTC)
    settings = SimpleNamespace(
        user_id=7,
        output_language="English",
        auto_execute_signals=False,
        active_preset_name="old",
        webhook_url=None,
        updated_at=updated_at,
    )

    async def fake_get_settings(_db, _user):
        return settings

    async def fake_emit(*args, **kwargs):
        emitted.append((args, kwargs))

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_get_settings)
    monkeypatch.setattr("backend.core.events.emit", fake_emit)
    db = _Db()

    result = await apply_preset_to_settings(
        db,
        SimpleNamespace(id=7),
        SimpleNamespace(name="new", settings_json='{"output_language":"English"}'),
    )

    assert result == "new"
    assert settings.active_preset_name == "new"
    assert settings.updated_at > updated_at
    assert db.flushes == 1
    assert db.commits == 1
    assert emitted == []
