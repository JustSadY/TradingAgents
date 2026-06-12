"""Tests for encrypted per-user API key management (``user_service``)."""

from types import SimpleNamespace

from cryptography.fernet import Fernet

from backend.services import user_service as svc

FERNET = Fernet(Fernet.generate_key())
OTHER_FERNET = Fernet(Fernet.generate_key())


def _user(api_keys_enc=None):
    return SimpleNamespace(id=1, api_keys_enc=api_keys_enc)


def test_set_then_get_round_trips():
    user = _user()
    svc.set_user_api_key(user, "OpenAI", "sk-123", FERNET)
    assert user.api_keys_enc  # stored as ciphertext, not plaintext
    assert "sk-123" not in user.api_keys_enc
    assert svc.get_user_api_key(user, "openai", FERNET) == "sk-123"


def test_provider_lookup_is_case_insensitive():
    user = _user()
    svc.set_user_api_key(user, "ANTHROPIC", "key-a", FERNET)
    assert svc.get_user_api_key(user, "Anthropic", FERNET) == "key-a"


def test_get_returns_none_without_keys_or_for_unknown_provider():
    assert svc.get_user_api_key(_user(), "openai", FERNET) is None
    user = _user()
    svc.set_user_api_key(user, "openai", "sk-123", FERNET)
    assert svc.get_user_api_key(user, "google", FERNET) is None


def test_wrong_encryption_key_fails_soft():
    user = _user()
    svc.set_user_api_key(user, "openai", "sk-123", FERNET)
    # e.g. ENCRYPTION_KEY rotated without re-encrypting stored blobs.
    assert svc.get_user_api_key(user, "openai", OTHER_FERNET) is None
    assert svc.list_user_api_key_providers(user, OTHER_FERNET) == []
    assert svc.delete_user_api_key(user, "openai", OTHER_FERNET) is False


def test_set_on_undecryptable_blob_reinitializes():
    user = _user(api_keys_enc="garbage")
    svc.set_user_api_key(user, "openai", "sk-new", FERNET)
    assert svc.get_user_api_key(user, "openai", FERNET) == "sk-new"


def test_set_preserves_other_providers():
    user = _user()
    svc.set_user_api_key(user, "openai", "sk-1", FERNET)
    svc.set_user_api_key(user, "anthropic", "sk-2", FERNET)
    svc.set_user_api_key(user, "openai", "sk-1b", FERNET)  # overwrite
    assert svc.get_user_api_key(user, "openai", FERNET) == "sk-1b"
    assert svc.get_user_api_key(user, "anthropic", FERNET) == "sk-2"


def test_delete_removes_provider_and_clears_blob_when_last():
    user = _user()
    svc.set_user_api_key(user, "openai", "sk-1", FERNET)
    svc.set_user_api_key(user, "anthropic", "sk-2", FERNET)

    assert svc.delete_user_api_key(user, "OpenAI", FERNET) is True
    assert svc.get_user_api_key(user, "openai", FERNET) is None
    assert svc.get_user_api_key(user, "anthropic", FERNET) == "sk-2"

    # Removing the last key clears the stored blob entirely.
    assert svc.delete_user_api_key(user, "anthropic", FERNET) is True
    assert user.api_keys_enc is None

    assert svc.delete_user_api_key(user, "anthropic", FERNET) is False


def test_list_providers_names_only():
    user = _user()
    svc.set_user_api_key(user, "openai", "sk-1", FERNET)
    svc.set_user_api_key(user, "google", "sk-2", FERNET)
    providers = svc.list_user_api_key_providers(user, FERNET)
    assert sorted(providers) == ["google", "openai"]
    # The listing must never expose key material.
    assert "sk-1" not in providers and "sk-2" not in providers
