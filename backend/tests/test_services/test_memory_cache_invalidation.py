from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from cryptography.fernet import Fernet

import backend.services.memory_service as memory_service
import backend.services.user_service as user_service
from backend.schemas.settings import SettingsUpdate
from backend.services.settings_service import apply_settings_update
from backend.services.user_service import remove_stored_api_key, save_stored_api_key


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


async def test_memory_store_setting_change_invalidates_only_that_user(monkeypatch) -> None:
    invalidated: list[int | None] = []
    monkeypatch.setattr(memory_service, "invalidate_user_memory_store_cache", invalidated.append)
    monkeypatch.setattr("backend.core.events.emit", _noop_emit)

    settings = SimpleNamespace(
        user_id=7,
        memory_embedder="openai",
        auto_execute_signals=False,
        active_preset_name="baseline",
        webhook_url=None,
        updated_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
    )
    db = _Db()

    await apply_settings_update(db, settings, SettingsUpdate(memory_embedder="ollama"))

    assert invalidated == [7]
    assert settings.memory_embedder == "ollama"
    assert db.flushes == 1
    assert db.commits == 1


async def test_unrelated_setting_change_does_not_invalidate_memory_store(monkeypatch) -> None:
    invalidated: list[int | None] = []
    monkeypatch.setattr(memory_service, "invalidate_user_memory_store_cache", invalidated.append)
    monkeypatch.setattr("backend.core.events.emit", _noop_emit)

    settings = SimpleNamespace(
        user_id=7,
        output_language="English",
        auto_execute_signals=False,
        active_preset_name=None,
        webhook_url=None,
        updated_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
    )

    await apply_settings_update(_Db(), settings, SettingsUpdate(output_language="Turkish"))

    assert invalidated == []


async def test_openai_key_rotation_invalidates_memory_store_but_other_keys_do_not(monkeypatch) -> None:
    invalidated: list[int | None] = []
    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr(user_service, "_app_fernet", lambda: fernet)
    monkeypatch.setattr(memory_service, "invalidate_user_memory_store_cache", invalidated.append)

    db = _Db()
    user = SimpleNamespace(id=7, api_keys_enc=None)

    await save_stored_api_key(db, user, "openai", "sk-openai")
    assert invalidated == [7]
    assert db.flushes == 1

    invalidated.clear()
    ciphertext = user.api_keys_enc
    await save_stored_api_key(db, user, "openai", "sk-openai")
    assert user.api_keys_enc == ciphertext
    assert invalidated == []
    assert db.flushes == 1

    await save_stored_api_key(db, user, "anthropic", "sk-anthropic")
    assert invalidated == []
    assert db.flushes == 2

    assert await remove_stored_api_key(db, user, "openai") is True
    assert invalidated == [7]
    assert db.flushes == 3
