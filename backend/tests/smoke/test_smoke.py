import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"status": "ok"}

@pytest.mark.asyncio
async def test_db_session_injects(db_session):
    """Verify the test DB fixture works with raw SQL."""
    from sqlalchemy import text

    result = await db_session.execute(text("SELECT 1 AS val"))
    row = result.one()
    assert row.val == 1

@pytest.mark.asyncio
async def test_auth_token_created(test_user, auth_token):
    """Verify token generation and user fixture work."""
    from backend.core.security import decode_token

    username = decode_token(auth_token)
    assert username == test_user.username

@pytest.mark.asyncio
async def test_authenticated_client_works(authenticated_client: AsyncClient):
    """Verify auth headers propagate through the test client."""
    resp = await authenticated_client.get("/health")
    assert resp.status_code == 200
