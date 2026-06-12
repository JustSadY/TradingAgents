"""Tests for per-user settings business logic (``settings_service``)."""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.settings import SettingsUpdate
from backend.services import settings_service as svc


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def user(db):
    u = User(username="alice", hashed_password="x", role="user")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_get_or_create_settings_is_lazy_and_idempotent(db, user):
    first = await svc.get_or_create_settings(db, user)
    assert first.user_id == user.id

    second = await svc.get_or_create_settings(db, user)
    assert second.id == first.id

    rows = (await db.execute(select(AppSettings))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_global_settings_row_has_no_user(db):
    settings = await svc.get_or_create_settings(db, None)
    assert settings.user_id is None
    again = await svc.get_or_create_settings(db, None)
    assert again.id == settings.id


@pytest.mark.asyncio
async def test_user_rows_are_isolated_from_global_row(db, user):
    global_settings = await svc.get_or_create_settings(db, None)
    user_settings = await svc.get_or_create_settings(db, user)
    assert global_settings.id != user_settings.id


@pytest.mark.asyncio
async def test_real_change_detaches_active_preset(db, user):
    settings = await svc.get_or_create_settings(db, user)
    settings.active_preset_name = "aggressive"
    await db.flush()

    await svc.apply_settings_update(db, settings, SettingsUpdate(max_debate_rounds=3))
    assert settings.max_debate_rounds == 3
    assert settings.active_preset_name is None


@pytest.mark.asyncio
async def test_noop_update_keeps_active_preset(db, user):
    settings = await svc.get_or_create_settings(db, user)
    settings.max_debate_rounds = 3
    settings.active_preset_name = "aggressive"
    await db.flush()

    # Re-sending the current value is not a "real" edit.
    await svc.apply_settings_update(db, settings, SettingsUpdate(max_debate_rounds=3))
    assert settings.active_preset_name == "aggressive"


@pytest.mark.asyncio
async def test_setting_preset_name_alone_is_not_a_change(db, user):
    settings = await svc.get_or_create_settings(db, user)
    await svc.apply_settings_update(db, settings, SettingsUpdate(active_preset_name="balanced"))
    assert settings.active_preset_name == "balanced"


@pytest.mark.asyncio
async def test_get_user_language(db, user):
    assert await svc.get_user_language(db, None) == "English"

    settings = await svc.get_or_create_settings(db, user)
    settings.output_language = "Turkish"
    await db.flush()
    assert await svc.get_user_language(db, user) == "Turkish"


@pytest.mark.asyncio
async def test_get_user_language_falls_back_on_error(db, user, monkeypatch):
    async def boom(db_, user_):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "get_or_create_settings", boom)
    assert await svc.get_user_language(db, user) == "English"


@pytest.mark.asyncio
async def test_apply_preset_sets_known_fields_and_name(db, user):
    preset = SimpleNamespace(
        name="balanced",
        settings_json='{"max_debate_rounds": 2, "output_language": "Turkish", "not_a_field": 1, "watchlist": null}',
    )
    name = await svc.apply_preset_to_settings(db, user, preset)
    assert name == "balanced"

    settings = await svc.get_or_create_settings(db, user)
    assert settings.max_debate_rounds == 2
    assert settings.output_language == "Turkish"
    assert settings.active_preset_name == "balanced"
    # null values in the preset must not wipe existing settings.
    assert settings.watchlist == []


@pytest.mark.asyncio
async def test_apply_preset_with_invalid_json_raises(db, user):
    preset = SimpleNamespace(name="broken", settings_json="{not json")
    with pytest.raises(ValueError, match="Template JSON invalid"):
        await svc.apply_preset_to_settings(db, user, preset)


@pytest.mark.asyncio
async def test_watchlist_add_dedupes_and_remove_deletes(db, user):
    assert await svc.add_ticker_to_watchlist(db, user, "AAPL") == ["AAPL"]
    assert await svc.add_ticker_to_watchlist(db, user, "MSFT") == ["AAPL", "MSFT"]
    # Duplicate add is a no-op.
    assert await svc.add_ticker_to_watchlist(db, user, "AAPL") == ["AAPL", "MSFT"]
    assert await svc.remove_ticker_from_watchlist(db, user, "AAPL") == ["MSFT"]
    # Removing an absent ticker is harmless.
    assert await svc.remove_ticker_from_watchlist(db, user, "TSLA") == ["MSFT"]
