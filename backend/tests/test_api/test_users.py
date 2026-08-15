from __future__ import annotations

import pytest
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


@pytest.fixture
def tool_key() -> str:
    """Any registered tool key.

    The registry is populated by the app lifespan, which the test client does
    not run, so the bootstrap import has to be explicit here.
    """
    import backend.trading_agents.agents.tools.bootstrap  # noqa: F401
    from backend.trading_agents.agents.tools import registry

    tools = registry.list()
    assert tools, "tool registry bootstrap registered nothing"
    return tools[0].key


class TestToolAccessAPI:
    """The access maps are declared payloads now, not bare dicts.

    Both halves are worth pinning: the response has to keep every permission
    key so the admin UI can render it, and an unrecognised permission name has
    to stay a rejection rather than being quietly dropped.
    """

    async def test_tool_access_response_carries_every_permission(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_user: User,
        tool_key: str,
    ):
        async_client.headers.update(admin_headers)
        resp = await async_client.get(f"/api/users/{test_user.id}/tool-access")

        assert resp.status_code == 200
        assert resp.json()[tool_key] == {
            "can_view": True,
            "can_use": True,
            "can_edit": False,
            "can_enable": False,
        }

    async def test_partial_permission_update_leaves_the_others_alone(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_user: User,
        tool_key: str,
    ):
        async_client.headers.update(admin_headers)

        resp = await async_client.put(
            f"/api/users/{test_user.id}/tool-access", json={"tools": {tool_key: {"can_use": False}}}
        )

        assert resp.status_code == 200
        assert resp.json()["tools"][tool_key] == {
            "can_view": True,
            "can_use": False,
            "can_edit": False,
            "can_enable": False,
        }

    async def test_unknown_permission_name_is_rejected(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        test_user: User,
        tool_key: str,
    ):
        async_client.headers.update(admin_headers)

        resp = await async_client.put(
            f"/api/users/{test_user.id}/tool-access", json={"tools": {tool_key: {"can_teleport": True}}}
        )

        assert resp.status_code == 422
