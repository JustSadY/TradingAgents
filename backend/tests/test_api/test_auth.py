from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.password_hashing import hash_password
from backend.core.security import create_refresh_token, new_token_id, token_id_hash
from backend.models.refresh_session import RefreshSession
from backend.models.user import User


async def issue_refresh_token(db: AsyncSession, user: User, *, token_version: int | None = None) -> str:
    """Mint a refresh token *and* the RefreshSession row it is bound to.

    ``/auth/refresh`` looks the ``sid`` up in ``refresh_sessions`` and compares
    the presented ``jti`` against the stored hash, so a token forged without a
    matching row is rejected as "session expired or reused". Tests that assert a
    *later* rejection reason (e.g. token-version revocation) would otherwise pass
    for the wrong reason.
    """
    settings = get_settings()
    sid, jti = new_token_id(), new_token_id()
    db.add(
        RefreshSession(
            id=sid,
            user_id=user.id,
            current_jti_hash=token_id_hash(jti),
            expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    await db.flush()
    version = user.token_version if token_version is None else token_version
    return create_refresh_token(user.username, token_version=version, session_id=sid, token_id=jti)


class TestAuthAPI:
    async def test_login_upgrades_a_legacy_bcrypt_hash_to_argon2(
        self, async_client: AsyncClient, db: AsyncSession
    ):
        """Accounts created before the Argon2 migration still hold bcrypt hashes.
        Logging in must succeed and re-store the password under Argon2, so the
        legacy scheme drains away instead of persisting indefinitely.
        """
        import bcrypt

        legacy_hash = bcrypt.hashpw(b"correctpass", bcrypt.gensalt()).decode()
        user = User(
            username="legacyhash",
            hashed_password=legacy_hash,
            email="legacy@example.com",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        resp = await async_client.post(
            "/auth/login", json={"username": "legacyhash", "password": "correctpass"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"

        await db.refresh(user)
        assert user.hashed_password.startswith("$argon2")
        assert user.hashed_password != legacy_hash

        # The re-stored hash must still authenticate the same password.
        again = await async_client.post(
            "/auth/login", json={"username": "legacyhash", "password": "correctpass"}
        )
        assert again.status_code == 200

    async def test_login_rejects_wrong_password_for_legacy_bcrypt_hash(
        self, async_client: AsyncClient, db: AsyncSession
    ):
        import bcrypt

        db.add(
            User(
                username="legacywrong",
                hashed_password=bcrypt.hashpw(b"correctpass", bcrypt.gensalt()).decode(),
                email="legacywrong@example.com",
                role="user",
                is_active=True,
            )
        )
        await db.flush()

        resp = await async_client.post(
            "/auth/login", json={"username": "legacywrong", "password": "wrongpass"}
        )
        assert resp.status_code == 401

    async def test_login_success_sets_httponly_refresh_cookie(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="logintest",
            hashed_password=hash_password("correctpass"),
            email="login@example.com",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        resp = await async_client.post("/auth/login", json={"username": "logintest", "password": "correctpass"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" not in data
        assert data["token_type"] == "bearer"
        cookie = resp.headers.get("set-cookie", "").lower()
        assert "ta_refresh=" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie

    async def test_login_wrong_password(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="loginfail",
            hashed_password=hash_password("correctpass"),
            email="fail@example.com",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        resp = await async_client.post("/auth/login", json={"username": "loginfail", "password": "wrongpass"})
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, async_client: AsyncClient):
        resp = await async_client.post("/auth/login", json={"username": "ghost", "password": "anypass"})
        assert resp.status_code == 401

    async def test_login_inactive_user(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="inactiveuser",
            hashed_password=hash_password("pass"),
            email="inactive@example.com",
            role="user",
            is_active=False,
        )
        db.add(user)
        await db.flush()
        resp = await async_client.post("/auth/login", json={"username": "inactiveuser", "password": "pass"})
        assert resp.status_code == 401

    async def test_refresh_token_cookie_success(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="refreshtest",
            hashed_password=hash_password("pass"),
            email="refresh@example.com",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        refresh = await issue_refresh_token(db, user)
        async_client.cookies.set("ta_refresh", refresh, path="/auth")
        resp = await async_client.post("/auth/refresh", json={})
        assert resp.status_code == 200
        assert "access_token" in resp.json()
        assert "refresh_token" not in resp.json()
        assert "httponly" in resp.headers.get("set-cookie", "").lower()
        await db.refresh(user)
        assert user.token_version == 0  # normal refresh must not invalidate other browser tabs

    async def test_refresh_body_token_remains_compatible(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="apiclient",
            hashed_password=hash_password("pass"),
            email="api@example.com",
            role="user",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        refresh = await issue_refresh_token(db, user)
        resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_token_invalid(self, async_client: AsyncClient):
        resp = await async_client.post("/auth/refresh", json={"refresh_token": "invalid-token"})
        assert resp.status_code == 401

    async def test_refresh_token_missing(self, async_client: AsyncClient):
        resp = await async_client.post("/auth/refresh", json={})
        assert resp.status_code == 401

    async def test_refresh_token_revoked(self, async_client: AsyncClient, db: AsyncSession):
        user = User(
            username="revokedtest",
            hashed_password=hash_password("pass"),
            email="revoked@example.com",
            role="user",
            is_active=True,
            token_version=5,
        )
        db.add(user)
        await db.flush()
        # Session is valid; only the stale token_version (0 vs the user's 5)
        # may cause the rejection.
        refresh = await issue_refresh_token(db, user, token_version=0)
        resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Refresh token has been revoked"

    async def test_logout_clears_refresh_cookie(self, auth_client: AsyncClient, db: AsyncSession, test_user: User):
        resp = await auth_client.post("/auth/logout")
        assert resp.status_code == 204
        cookie = resp.headers.get("set-cookie", "").lower()
        assert "ta_refresh=" in cookie and "max-age=0" in cookie

    async def test_protected_endpoint_no_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/analysis/history")
        assert resp.status_code == 401

    async def test_protected_endpoint_with_auth(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/analysis/history")
        assert resp.status_code == 200
