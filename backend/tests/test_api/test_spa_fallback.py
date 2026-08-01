from httpx import AsyncClient

async def test_unknown_api_paths_are_not_masked_by_the_spa(async_client: AsyncClient):
    """A typo under /api must be observable as 404, never index.html."""
    response = await async_client.get("/api/does-not-exist")

    assert response.status_code == 404

async def test_api_root_is_not_masked_by_the_spa(async_client: AsyncClient):
    response = await async_client.get("/api")

    assert response.status_code == 404
