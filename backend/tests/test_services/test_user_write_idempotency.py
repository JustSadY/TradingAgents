from __future__ import annotations

from types import SimpleNamespace

import backend.services.settings_service as settings_service
import backend.services.user_service as user_service
from backend.repositories.users import update_user_admin, update_user_profile
from backend.services.settings_service import remove_ticker_from_watchlist
from backend.services.user_service import update_profile


class _Db:
    def __init__(self) -> None:
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


async def test_profile_same_email_skips_uniqueness_query(monkeypatch) -> None:
    user = SimpleNamespace(
        id=7,
        email="same@example.com",
        display_name="Same Name",
        token_version=0,
    )

    async def email_must_not_run(*_args, **_kwargs):
        raise AssertionError("same email must not perform uniqueness query")

    async def fake_update(_db, received_user, **kwargs):
        assert kwargs == {
            "email": "same@example.com",
            "display_name": "Same Name",
            "hashed_password": None,
        }
        return received_user

    monkeypatch.setattr("backend.repositories.users.email_exists", email_must_not_run)
    monkeypatch.setattr("backend.repositories.users.update_user_profile", fake_update)

    result = await update_profile(
        object(),
        user,
        email="same@example.com",
        display_name="Same Name",
        password=None,
    )

    assert result is user


async def test_repository_profile_and_admin_updates_skip_unchanged_flushes() -> None:
    db = _Db()
    user = SimpleNamespace(
        email="same@example.com",
        display_name="Same Name",
        hashed_password="hash",
        role="user",
        is_active=True,
    )

    await update_user_profile(
        db,
        user,
        email="same@example.com",
        display_name="Same Name",
        hashed_password=None,
    )
    await update_user_admin(
        db,
        user,
        role="user",
        is_active=True,
        email="same@example.com",
        display_name="Same Name",
    )

    assert db.flushes == 0


async def test_missing_watchlist_ticker_is_a_noop(monkeypatch) -> None:
    settings = SimpleNamespace(watchlist=["AAPL", "MSFT"])

    async def fake_settings(_db, _user):
        return settings

    monkeypatch.setattr(settings_service, "get_or_create_settings", fake_settings)
    db = _Db()

    result = await remove_ticker_from_watchlist(db, SimpleNamespace(id=7), "NVDA")

    assert result == ["AAPL", "MSFT"]
    assert settings.watchlist == ["AAPL", "MSFT"]
    assert db.flushes == 0
