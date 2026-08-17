from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.password_hashing import verify_password
from backend.models.user import User
from backend.services.user_service import (
    CannotDeleteSelfError,
    UserNotFoundError,
    UserPolicyError,
    UsernameTakenError,
    create_managed_user,
    decrypt_api_keys,
    delete_managed_user,
    delete_user_api_key,
    encrypt_api_keys,
    get_user_api_key,
    list_user_api_key_providers,
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
        assert verify_password("new-secure-password", updated.hashed_password)

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
