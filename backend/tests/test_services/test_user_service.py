from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.constants import PAGE_KEYS, SETTING_KEYS
from backend.core.password_hashing import verify_and_update_password
from backend.models.user import User
from backend.services.user_service import (
    CannotDeleteSelfError,
    UnknownPermissionKeysError,
    UsernameTakenError,
    UserNotFoundError,
    UserPolicyError,
    create_managed_user,
    decrypt_api_keys,
    delete_managed_user,
    delete_user_api_key,
    encrypt_api_keys,
    get_effective_page_permissions,
    get_effective_setting_permissions,
    get_managed_page_permissions,
    get_user_api_key,
    list_stored_api_key_providers,
    list_user_api_key_providers,
    remove_stored_api_key,
    save_stored_api_key,
    set_managed_page_permissions,
    set_managed_setting_permissions,
    set_user_api_key,
    update_managed_user,
    update_profile,
)


class TestUserService:
    def setup_method(self):
        self.fernet = Fernet(Fernet.generate_key())
        self.test_keys = {"openai": "sk-test123", "anthropic": "sk-ant-test456"}

    def test_encrypt_decrypt_cycle(self):
        encrypted = encrypt_api_keys(self.test_keys, self.fernet)
        assert isinstance(encrypted, str)
        assert encrypted != ""

        decrypted = decrypt_api_keys(encrypted, self.fernet)
        assert decrypted == self.test_keys

    def test_decrypt_invalid_data_raises(self):
        with pytest.raises(InvalidToken):
            decrypt_api_keys("invalid-data", self.fernet)

    def test_get_user_api_key(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        key = get_user_api_key(user, "openai", self.fernet)
        assert key == "sk-test123"

    def test_get_user_api_key_case_insensitive(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        key = get_user_api_key(user, "OpenAI", self.fernet)
        assert key == "sk-test123"

    def test_get_user_api_key_missing_provider(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        key = get_user_api_key(user, "nonexistent", self.fernet)
        assert key is None

    def test_server_managed_provider_key_is_inert_and_not_listed(self):
        user = User(api_keys_enc=encrypt_api_keys({"ollama": "http://stale.internal"}, self.fernet))

        assert get_user_api_key(user, "ollama", self.fernet) is None
        assert list_user_api_key_providers(user, self.fernet) == []

    def test_server_managed_provider_key_cannot_be_stored(self):
        user = User(api_keys_enc=None)

        with pytest.raises(ValueError, match="server-managed"):
            set_user_api_key(user, "ollama", "http://stale.internal", self.fernet)

        assert user.api_keys_enc is None

    def test_get_user_api_key_no_keys_stored(self):
        user = User(api_keys_enc=None)
        key = get_user_api_key(user, "openai", self.fernet)
        assert key is None

    def test_get_user_api_key_corrupted_data(self):
        user = User(api_keys_enc="corrupted-data")
        key = get_user_api_key(user, "openai", self.fernet)
        assert key is None

    def test_set_user_api_key_new(self):
        user = User(api_keys_enc=None)
        set_user_api_key(user, "openai", "sk-new-key", self.fernet)
        assert user.api_keys_enc is not None
        keys = decrypt_api_keys(user.api_keys_enc, self.fernet)
        assert keys == {"openai": "sk-new-key"}

    def test_set_user_api_key_append(self):
        user = User(api_keys_enc=encrypt_api_keys({"openai": "sk-old"}, self.fernet))
        set_user_api_key(user, "anthropic", "sk-ant-new", self.fernet)
        keys = decrypt_api_keys(user.api_keys_enc, self.fernet)
        assert keys == {"openai": "sk-old", "anthropic": "sk-ant-new"}

    def test_set_user_api_key_overwrite(self):
        user = User(api_keys_enc=encrypt_api_keys({"openai": "sk-old"}, self.fernet))
        set_user_api_key(user, "openai", "sk-new", self.fernet)
        keys = decrypt_api_keys(user.api_keys_enc, self.fernet)
        assert keys == {"openai": "sk-new"}

    def test_delete_user_api_key(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        result = delete_user_api_key(user, "openai", self.fernet)
        assert result is True
        keys = decrypt_api_keys(user.api_keys_enc, self.fernet)
        assert "openai" not in keys
        assert "anthropic" in keys

    def test_delete_user_api_key_last_key_clears_enc(self):
        user = User(api_keys_enc=encrypt_api_keys({"openai": "sk-only"}, self.fernet))
        result = delete_user_api_key(user, "openai", self.fernet)
        assert result is True
        assert user.api_keys_enc is None

    def test_delete_user_api_key_not_found(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        result = delete_user_api_key(user, "nonexistent", self.fernet)
        assert result is False

    def test_delete_user_api_key_no_keys(self):
        user = User(api_keys_enc=None)
        result = delete_user_api_key(user, "openai", self.fernet)
        assert result is False

    def test_list_user_api_key_providers(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))
        providers = list_user_api_key_providers(user, self.fernet)
        assert sorted(providers) == ["anthropic", "openai"]

    def test_list_user_api_key_providers_empty(self):
        user = User(api_keys_enc=None)
        providers = list_user_api_key_providers(user, self.fernet)
        assert providers == []

    def test_list_user_api_key_providers_corrupted(self):
        user = User(api_keys_enc="corrupted")
        providers = list_user_api_key_providers(user, self.fernet)
        assert providers == []

    def test_resolve_user_api_key(self):
        encrypted = encrypt_api_keys({"openai": "sk-resolve"}, self.fernet)
        user = User(api_keys_enc=encrypted)

        with patch("backend.core.config.get_settings") as mock_settings:
            mock_settings.return_value.get_fernet.return_value = self.fernet
            from backend.services.user_service import resolve_user_api_key

            key = resolve_user_api_key(user, "openai")
            assert key == "sk-resolve"

    def test_list_stored_api_key_providers_owns_fernet_lookup(self):
        user = User(api_keys_enc=encrypt_api_keys(self.test_keys, self.fernet))

        with patch("backend.core.config.get_settings") as mock_settings:
            mock_settings.return_value.get_fernet.return_value = self.fernet
            assert sorted(list_stored_api_key_providers(user)) == ["anthropic", "openai"]

    async def test_save_and_remove_stored_api_key_own_persistence_boundary(
        self,
        db: AsyncSession,
        test_user: User,
    ) -> None:
        with patch("backend.core.config.get_settings") as mock_settings:
            mock_settings.return_value.get_fernet.return_value = self.fernet
            await save_stored_api_key(db, test_user, "openai", "sk-service")
            assert decrypt_api_keys(test_user.api_keys_enc, self.fernet)["openai"] == "sk-service"

            assert await remove_stored_api_key(db, test_user, "openai") is True
            assert test_user.api_keys_enc is None

    async def test_update_profile_password_invalidates_old_tokens(
        self,
        db: AsyncSession,
        test_user: User,
    ) -> None:
        before_version = test_user.token_version

        updated = await update_profile(
            db,
            test_user,
            email=None,
            display_name=None,
            password="new-secure-password",
        )

        assert updated.token_version == before_version + 1
        assert verify_and_update_password("new-secure-password", updated.hashed_password)[0]

    async def test_create_managed_user_rejects_duplicate_username(
        self,
        db: AsyncSession,
        admin_user: User,
        test_user: User,
    ) -> None:
        with pytest.raises(UsernameTakenError, match="Username already taken"):
            await create_managed_user(
                db,
                admin_user,
                username=test_user.username,
                password="password123",
                email=None,
                display_name=None,
                role="user",
            )

    async def test_non_owner_admin_cannot_create_an_admin(
        self,
        db: AsyncSession,
        admin_user: User,
    ) -> None:
        assert admin_user.role == "admin"

        with pytest.raises(UserPolicyError, match="Server Owner"):
            await create_managed_user(
                db,
                admin_user,
                username="blocked-admin",
                password="password123",
                email=None,
                display_name=None,
                role="admin",
            )

    async def test_update_managed_user_rejects_missing_user(
        self,
        db: AsyncSession,
        admin_user: User,
    ) -> None:
        with pytest.raises(UserNotFoundError, match="User not found"):
            await update_managed_user(
                db,
                admin_user,
                999999,
                role=None,
                is_active=None,
                email=None,
                display_name=None,
            )

    async def test_delete_managed_user_rejects_self_delete(
        self,
        db: AsyncSession,
        admin_user: User,
    ) -> None:
        with pytest.raises(CannotDeleteSelfError, match="Cannot delete yourself"):
            await delete_managed_user(db, admin_user, admin_user.id)

    async def test_admin_effective_page_permissions_include_admin_page(
        self,
        db: AsyncSession,
        admin_user: User,
    ) -> None:
        assert await get_effective_page_permissions(db, admin_user) == [*PAGE_KEYS, "admin"]

    async def test_admin_effective_setting_permissions_are_all_settings(
        self,
        db: AsyncSession,
        admin_user: User,
    ) -> None:
        assert await get_effective_setting_permissions(db, admin_user) == list(SETTING_KEYS)

    async def test_managed_page_permissions_require_existing_user(
        self,
        db: AsyncSession,
    ) -> None:
        with pytest.raises(UserNotFoundError, match="User not found"):
            await get_managed_page_permissions(db, 999999)

    async def test_unknown_page_permission_key_is_rejected_in_service(
        self,
        db: AsyncSession,
        test_user: User,
    ) -> None:
        with pytest.raises(UnknownPermissionKeysError, match="Unknown page permission keys"):
            await set_managed_page_permissions(db, test_user.id, {"teleport": True})

    async def test_unknown_setting_permission_key_is_rejected_in_service(
        self,
        db: AsyncSession,
        test_user: User,
    ) -> None:
        with pytest.raises(UnknownPermissionKeysError, match="Unknown setting permission keys"):
            await set_managed_setting_permissions(db, test_user.id, {"teleport": True})


def test_users_router_keeps_persistence_and_request_models_out() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "api" / "users.py").read_text()

    assert "backend.repositories" not in source
    assert "backend.core.config" not in source
    assert "_get_settings" not in source
    assert "await db.flush()" not in source
    assert "from pydantic import BaseModel" not in source
    assert "list_stored_api_key_providers(" in source
    assert "save_stored_api_key(" in source
    assert "remove_stored_api_key(" in source


def test_user_cleanup_service_has_no_direct_sql_or_delete() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "user_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "select(AnalysisResult" not in source
    assert "await db.delete(user)" not in source
    assert "backend.repositories.user_cleanup" in source


def test_tool_access_service_uses_repository_for_sql() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    source = (backend_root / "services" / "tool_access_service.py").read_text()

    assert "from sqlalchemy import select" not in source
    assert "backend.models.tool_settings" not in source
    assert "backend.repositories.tool_access" in source
