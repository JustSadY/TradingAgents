from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from backend.schemas.settings import SettingsUpdate
from backend.services.settings_service import apply_settings_update


class _Db:
    def __init__(self) -> None:
        self.flushes = 0
        self.commits = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        self.commits += 1


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
