from __future__ import annotations

from httpx import AsyncClient

from backend.models.user import User

class TestUserApiKeysAPI:
    async def test_set_api_key_response_matches_schema(self, auth_client: AsyncClient):
        resp = await auth_client.put("/api/users/me/api-keys", json={"provider": "openai", "api_key": "sk-test-123"})
        assert resp.status_code == 200
        assert resp.json() == {"detail": "API key for 'openai' saved"}

    async def test_get_api_key_providers_after_set(self, auth_client: AsyncClient):
        await auth_client.put("/api/users/me/api-keys", json={"provider": "openai", "api_key": "sk-test-123"})

        resp = await auth_client.get("/api/users/me/api-keys")
        assert resp.status_code == 200
        assert resp.json() == {"providers": ["openai"]}

    async def test_delete_api_key_response_matches_schema(self, auth_client: AsyncClient):
        await auth_client.put("/api/users/me/api-keys", json={"provider": "openai", "api_key": "sk-test-123"})

        resp = await auth_client.delete("/api/users/me/api-keys/openai")
        assert resp.status_code == 200
        assert resp.json() == {"detail": "API key for 'openai' deleted"}

    async def test_delete_missing_api_key_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete("/api/users/me/api-keys/nonexistent")
        assert resp.status_code == 404

    async def test_update_permissions_response_matches_schema(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_user: User,
    ):
        async_client.headers.update(admin_headers)
        resp = await async_client.put(
            f"/api/users/{test_user.id}/permissions", json={"permissions": {"dashboard": True}}
        )
        assert resp.status_code == 200
        assert resp.json() == {"detail": "Permissions updated"}
