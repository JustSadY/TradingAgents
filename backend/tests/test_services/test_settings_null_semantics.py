"""Regression coverage for explicit-null settings and preset behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.preset import ConfigPreset
from backend.schemas.settings import SettingsUpdate
from backend.services import settings_service


def test_settings_update_allows_omission_but_rejects_null_for_non_nullable_field() -> None:
    assert SettingsUpdate().model_dump(exclude_unset=True) == {}
    assert SettingsUpdate(benchmark_ticker=None).model_dump(exclude_unset=True) == {"benchmark_ticker": None}

    with pytest.raises(ValidationError, match="cron_enabled may not be null"):
        SettingsUpdate(cron_enabled=None)

    with pytest.raises(ValidationError, match="active_preset_name"):
        SettingsUpdate(active_preset_name="manually-selected")

async def test_preset_can_clear_nullable_settings(monkeypatch) -> None:
    class Settings:
        benchmark_ticker = "SPY"
        openai_reasoning_effort = "high"
        webhook_url = None
        active_preset_name = None
        updated_at = None

    class Db:
        flushed = False
        committed = False

        async def flush(self) -> None:
            self.flushed = True

        async def commit(self) -> None:
            self.committed = True

    async def no_event(*_args, **_kwargs) -> None:
        return None

    async def get_settings(*_args):
        return settings

    settings = Settings()
    db = Db()
    monkeypatch.setattr(settings_service, "get_or_create_settings", get_settings)
    monkeypatch.setattr("backend.core.events.emit", no_event)

    preset = ConfigPreset(
        user_id=1,
        name="clear-optional-settings",
        settings_json='{"benchmark_ticker":null,"openai_reasoning_effort":null}',
    )

    await settings_service.apply_preset_to_settings(db, object(), preset)

    assert settings.benchmark_ticker is None
    assert settings.openai_reasoning_effort is None
    assert settings.active_preset_name == "clear-optional-settings"
    assert db.flushed is True
    assert db.committed is True
