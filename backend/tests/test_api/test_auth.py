from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import create_refresh_token, hash_password
from backend.models.user import User


class TestAuthAPI:
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

        refresh = create_refresh_token(user.username, token_version=0)
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
        refresh = create_refresh_token(user.username, token_version=0)
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
        refresh = create_refresh_token(user.username, token_version=0)
        resp = await async_client.post("/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 401

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
