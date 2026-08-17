from __future__ import annotations

import pytest

from backend.core.password_hashing import (
    hash_password,
    is_supported_password_hash,
    verify_and_update_password,
    verify_password,
)
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token_payload,
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

    def test_new_passwords_are_hashed_with_argon2(self):
        assert hash_password("testpassword").startswith("$argon2")

    def test_long_password_round_trip(self):
        password = "ş" * 40
        assert len(password) == 40
        assert len(password.encode()) == 80

        hashed = hash_password(password)
        assert verify_password(password, hashed) is True
        assert verify_password("ş" * 39, hashed) is False

    def test_argon2_hash_is_not_needlessly_rehashed(self):
        ok, upgraded = verify_and_update_password("testpassword", hash_password("testpassword"))
        assert ok is True
        assert upgraded is None

    def test_failed_verification_never_yields_an_upgrade(self):
        assert verify_and_update_password("anything", "not-a-valid-hash") == (False, None)

    def test_bcrypt_hash_is_not_supported(self):
        assert is_supported_password_hash("$2b$12$" + "a" * 53) is False
        assert verify_password("correctpass", "$2b$12$" + "a" * 53) is False

    @pytest.mark.parametrize(
        "value,supported",
        [
            ("$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2g", True),
            ("$2b$12$" + "a" * 53, False),
            ("plaintext-password", False),
            ("$unknown$whatever", False),
            ("", False),
        ],
    )
    def test_is_supported_password_hash(self, value, supported):
        assert is_supported_password_hash(value) is supported

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
        token = create_refresh_token("testuser", session_id="sess-1", token_id="jti-1")
        assert token is not None
        payload = decode_token_payload(token, "refresh")
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_refresh_token_carries_session_and_token_identity(self):
        """``sid``/``jti`` are what make a refresh token individually revocable.

        Losing either claim would silently turn rotation back into a plain
        long-lived token, so assert they survive the encode/decode round trip.
        """
        token = create_refresh_token("testuser", session_id="sess-abc", token_id="jti-xyz")
        payload = decode_token_payload(token, "refresh")
        assert payload["sid"] == "sess-abc"
        assert payload["jti"] == "jti-xyz"

    def test_decode_token_payload_wrong_type(self):
        token = create_access_token("testuser")
        with pytest.raises(ValueError, match="Wrong token type"):
            decode_token_payload(token, "refresh")

    def test_decode_token_payload_invalid(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token_payload("invalid-token", "access")

    def test_decode_token_payload_empty(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token_payload("", "access")

    def test_access_refresh_token_roundtrip(self):
        access = create_access_token("testuser", role="user", token_version=1)
        refresh = create_refresh_token("testuser", token_version=1, session_id="sess-1", token_id="jti-1")

        access_payload = decode_token_payload(access, "access")
        refresh_payload = decode_token_payload(refresh, "refresh")

        assert access_payload["sub"] == refresh_payload["sub"]
        assert access_payload["ver"] == refresh_payload["ver"] == 1
        assert access_payload["role"] == "user"
