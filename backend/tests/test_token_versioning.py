"""Tests for token versioning (logout / password-change revocation)."""

import pytest

from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_token_payload,
)


def test_access_token_carries_version():
    tok = create_access_token("alice", role="user", token_version=3)
    payload = decode_token_payload(tok, expected_type="access")
    assert payload["sub"] == "alice"
    assert payload["ver"] == 3
    assert payload["role"] == "user"


def test_refresh_token_carries_version():
    tok = create_refresh_token("bob", token_version=7)
    payload = decode_token_payload(tok, expected_type="refresh")
    assert payload["sub"] == "bob"
    assert payload["ver"] == 7


def test_decode_token_backward_compatible():
    # The legacy helper still returns just the username.
    tok = create_access_token("carol", token_version=0)
    assert decode_token(tok, expected_type="access") == "carol"


def test_wrong_token_type_rejected():
    refresh = create_refresh_token("dave", token_version=0)
    with pytest.raises(ValueError):
        decode_token_payload(refresh, expected_type="access")


def test_default_version_is_zero():
    tok = create_access_token("erin")
    assert decode_token_payload(tok)["ver"] == 0
