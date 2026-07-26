from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from backend.models.user import User
from backend.services.user_service import (
    decrypt_api_keys,
    delete_user_api_key,
    encrypt_api_keys,
    get_user_api_key,
    list_user_api_key_providers,
    set_user_api_key,
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
        with pytest.raises(Exception):
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

        with patch("backend.services.user_service.get_settings") as mock_settings:
            mock_settings.return_value.get_fernet.return_value = self.fernet
            from backend.services.user_service import resolve_user_api_key

            key = resolve_user_api_key(user, "openai")
            assert key == "sk-resolve"
