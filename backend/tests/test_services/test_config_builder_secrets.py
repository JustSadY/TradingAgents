from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from backend.core.security import encrypt_secret
from backend.services.analysis.config_builder import _decrypt_tool_secret, history_json_from


def test_tool_secret_decrypts_fernet_ciphertext() -> None:
    ciphertext = encrypt_secret("secret-value")

    assert _decrypt_tool_secret(ciphertext) == "secret-value"


def test_tool_secret_plaintext_is_rejected_after_data_migration() -> None:
    with pytest.raises(InvalidToken):
        _decrypt_tool_secret("legacy-plaintext-secret")


def test_tool_secret_empty_values_remain_empty() -> None:
    assert _decrypt_tool_secret(None) is None
    assert _decrypt_tool_secret("") == ""


def test_debate_side_history_is_persisted_as_structured_messages() -> None:
    assert history_json_from(
        "Bull Analyst: First line\ncontinues\nBear Analyst: Counterpoint"
    ) == [
        {"sender": "Bull Analyst", "content": "First line\ncontinues"},
        {"sender": "Bear Analyst", "content": "Counterpoint"},
    ]


def test_structured_debate_side_history_is_preserved() -> None:
    structured = [{"sender": "Bull Analyst", "content": "Already structured"}]

    assert history_json_from(structured) == structured


def test_invalid_debate_side_history_type_is_not_persisted() -> None:
    assert history_json_from(123) is None
