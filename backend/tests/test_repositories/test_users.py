from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.models.user import User
from backend.repositories.users import (
    create_user_with_permissions,
    email_exists,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    list_users,
    update_user_admin,
    update_user_profile,
    username_exists,
)


class TestUserRepository:
    async def test_create_user(self, db: AsyncSession):
        user = await create_user_with_permissions(
            db,
            username="newuser",
            hashed_password=hash_password("pass123"),
            email="new@example.com",
            display_name="New User",
            role="user",
        )
        assert user.id is not None
        assert user.username == "newuser"
        assert user.role == "user"
        assert user.is_active is True
        assert user.is_admin is False

    async def test_get_user_by_username(self, db: AsyncSession, test_user: User):
        found = await get_user_by_username(db, test_user.username)
        assert found is not None
        assert found.id == test_user.id
        assert found.username == test_user.username

    async def test_get_user_by_username_not_found(self, db: AsyncSession):
        found = await get_user_by_username(db, "nonexistent")
        assert found is None

    async def test_get_user_by_email(self, db: AsyncSession, test_user: User):
        found = await get_user_by_email(db, test_user.email)
        assert found is not None
        assert found.id == test_user.id

    async def test_get_user_by_email_not_found(self, db: AsyncSession):
        found = await get_user_by_email(db, "nonexistent@example.com")
        assert found is None

    async def test_get_user_by_id(self, db: AsyncSession, test_user: User):
        found = await get_user_by_id(db, test_user.id)
        assert found is not None
        assert found.username == test_user.username

    async def test_get_user_by_id_not_found(self, db: AsyncSession):
        found = await get_user_by_id(db, 99999)
        assert found is None

    async def test_username_exists(self, db: AsyncSession, test_user: User):
        assert await username_exists(db, test_user.username) is True
        assert await username_exists(db, "nonexistent") is False

    async def test_username_exists_exclude_self(self, db: AsyncSession, test_user: User):
        assert await username_exists(db, test_user.username, exclude_user_id=test_user.id) is False

    async def test_email_exists(self, db: AsyncSession, test_user: User):
        assert await email_exists(db, test_user.email) is True
        assert await email_exists(db, "nonexistent@example.com") is False

    async def test_email_exists_exclude_self(self, db: AsyncSession, test_user: User):
        assert await email_exists(db, test_user.email, exclude_user_id=test_user.id) is False

    async def test_list_users(self, db: AsyncSession, test_user: User, admin_user: User):
        all_users = await list_users(db)
        assert len(all_users) >= 2
        usernames = [u.username for u in all_users]
        assert test_user.username in usernames
        assert admin_user.username in usernames

    async def test_update_user_profile(self, db: AsyncSession, test_user: User):
        updated = await update_user_profile(
            db, test_user, email="updated@example.com", display_name="Updated Name"
        )
        assert updated.email == "updated@example.com"
        assert updated.display_name == "Updated Name"

    async def test_update_user_admin(self, db: AsyncSession, test_user: User):
        updated = await update_user_admin(db, test_user, role="admin", is_active=True)
        assert updated.role == "admin"
        assert updated.is_admin is True

    async def test_create_user_with_permissions(self, db: AsyncSession):
        from backend.models.page_permission import UserPagePermission, UserSettingPermission

        user = await create_user_with_permissions(
            db,
            username="permissions_test",
            hashed_password=hash_password("pass"),
            email="perm@example.com",
            display_name="Permissions Test",
            role="user",
        )
        from sqlalchemy import select

        page_perms = await db.execute(
            select(UserPagePermission).where(UserPagePermission.user_id == user.id)
        )
        pages = page_perms.scalars().all()
        page_keys = [p.page_key for p in pages]
        assert "dashboard" in page_keys
        assert "portfolio" in page_keys

        setting_perms = await db.execute(
            select(UserSettingPermission).where(UserSettingPermission.user_id == user.id)
        )
        assert len(setting_perms.scalars().all()) > 0
