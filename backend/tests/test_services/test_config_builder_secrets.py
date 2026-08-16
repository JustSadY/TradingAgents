from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from backend.core.security import encrypt_secret
from backend.services.analysis.config_builder import _decrypt_tool_secret


def test_tool_secret_decrypts_fernet_ciphertext() -> None:
    ciphertext = encrypt_secret("secret-value")

    assert _decrypt_tool_secret(ciphertext) == "secret-value"


def test_tool_secret_plaintext_is_rejected_after_data_migration() -> None:
    with pytest.raises(InvalidToken):
        _decrypt_tool_secret("legacy-plaintext-secret")


def test_tool_secret_empty_values_remain_empty() -> None:
    assert _decrypt_tool_secret(None) is None
    assert _decrypt_tool_secret("") == ""
