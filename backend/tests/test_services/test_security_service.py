from __future__ import annotations

import pytest

from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_token_payload,
    hash_password,
    verify_password,
)

class TestSecurityService:
    def test_hash_password(self):
        hashed = hash_password("testpassword")
        assert hashed != ""
        assert hashed != "testpassword"

    def test_verify_password_correct(self):
        hashed = hash_password("testpassword")
        assert verify_password("testpassword", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("testpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_invalid_hash(self):
        assert verify_password("test", "not-a-valid-hash") is False

    def test_create_access_token_default(self):
        token = create_access_token("testuser")
        assert token is not None
        payload = decode_token_payload(token, "access")
        assert payload["sub"] == "testuser"
        assert payload["role"] == "user"
        assert payload["type"] == "access"
        assert payload["ver"] == 0

    def test_create_access_token_with_role(self):
        token = create_access_token("adminuser", role="admin")
        payload = decode_token_payload(token, "access")
        assert payload["role"] == "admin"

    def test_create_access_token_with_version(self):
        token = create_access_token("testuser", token_version=5)
        payload = decode_token_payload(token, "access")
        assert payload["ver"] == 5

    def test_create_refresh_token(self):
        token = create_refresh_token("testuser")
        assert token is not None
        payload = decode_token_payload(token, "refresh")
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_decode_token(self):
        token = create_access_token("testuser")
        result = decode_token(token, "access")
        assert result == "testuser"

    def test_decode_token_wrong_type(self):
        token = create_access_token("testuser")
        with pytest.raises(ValueError, match="Wrong token type"):
            decode_token(token, "refresh")

    def test_decode_token_invalid(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("invalid-token", "access")

    def test_decode_token_empty(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("", "access")

    def test_access_refresh_token_roundtrip(self):
        access = create_access_token("testuser", role="user", token_version=1)
        refresh = create_refresh_token("testuser", token_version=1)

        access_payload = decode_token_payload(access, "access")
        refresh_payload = decode_token_payload(refresh, "refresh")

        assert access_payload["sub"] == refresh_payload["sub"]
        assert access_payload["ver"] == refresh_payload["ver"] == 1
        assert access_payload["role"] == "user"
