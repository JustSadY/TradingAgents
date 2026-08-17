"""First-run owner registration replaces the .env admin seed."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AsyncSessionLocal
from backend.models.page_permission import UserPagePermission, UserSettingPermission
from backend.models.user import User
from backend.services.first_run_service import (
    SetupAlreadyCompletedError,
    create_first_owner,
    owner_setup_required,
)


@pytest_asyncio.fixture
async def clean_committed_users():
    """Remove rows the setup service commits outside the rollback-only fixture.

    Request this fixture *first* in a test signature: the cleanup has to run
    after ``db_session`` rolls back, or its open write transaction locks the
    shared SQLite file and the DELETE fails.
    """
    yield
    async with AsyncSessionLocal() as db:
        # Deleted explicitly: this engine has no SQLite foreign-key pragma, so
        # the ON DELETE CASCADE the schema declares does not fire here.
        await db.execute(delete(UserPagePermission))
        await db.execute(delete(UserSettingPermission))
        await db.execute(delete(User))
        await db.commit()


class TestSetupStatus:
    async def test_reports_setup_required_on_an_empty_installation(self, async_client: AsyncClient):
        response = await async_client.get("/auth/setup-status")
        assert response.status_code == 200
        assert response.json() == {"setup_required": True}

    async def test_reports_completed_once_any_user_exists(self, async_client: AsyncClient, test_user: User):
        response = await async_client.get("/auth/setup-status")
        assert response.status_code == 200
        assert response.json() == {"setup_required": False}


class TestFirstOwnerRegistration:
    async def test_registers_the_owner_and_signs_it_in(
        self,
        clean_committed_users,
        async_client: AsyncClient,
    ):
        response = await async_client.post(
            "/auth/setup",
            json={"username": "founder", "password": "founder-pass-123", "email": "founder@example.com"},
        )

        assert response.status_code == 201
        assert isinstance(response.json()["access_token"], str)
        # The bootstrap credential is a session, not a value printed into logs
        # or parked in .env.
        assert "ta_refresh" in response.cookies

        async with AsyncSessionLocal() as db:
            created = (await db.execute(select(User).where(User.username == "founder"))).scalar_one()
            assert created.role == "owner"
            assert created.email == "founder@example.com"

    async def test_is_closed_once_an_account_exists(self, clean_committed_users):
        await create_first_owner(username="founder", password="founder-pass-123")

        with pytest.raises(SetupAlreadyCompletedError):
            await create_first_owner(username="second", password="another-pass-123")

        async with AsyncSessionLocal() as db:
            owners = (await db.execute(select(User))).scalars().all()
            assert [user.username for user in owners] == ["founder"]

    async def test_rejects_a_password_shorter_than_the_policy(self, async_client: AsyncClient):
        response = await async_client.post("/auth/setup", json={"username": "founder", "password": "short"})
        assert response.status_code == 422

    async def test_owner_setup_required_tracks_the_user_table(self, db: AsyncSession, test_user: User):
        assert await owner_setup_required(db) is False
