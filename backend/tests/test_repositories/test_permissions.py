from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.permissions import (
    get_user_page_permission,
    get_user_page_permissions_map,
    get_user_setting_permission,
    get_user_setting_permissions_map,
    list_allowed_page_keys,
    list_allowed_setting_sections,
    set_user_page_permission,
    set_user_setting_permission,
)


class TestPermissionsRepository:
    async def test_get_user_page_permission_default(self, db: AsyncSession, test_user):
        perm = await get_user_page_permission(db, test_user.id, "analysis")
        assert perm is None

    async def test_set_user_page_permission(self, db: AsyncSession, test_user):
        await set_user_page_permission(db, test_user.id, "analysis", True)

        perm = await get_user_page_permission(db, test_user.id, "analysis")
        assert perm is not None
        assert perm.allowed is True

    async def test_set_user_page_permission_toggle_off(self, db: AsyncSession, test_user):
        await set_user_page_permission(db, test_user.id, "analysis", True)
        await set_user_page_permission(db, test_user.id, "analysis", False)

        perm = await get_user_page_permission(db, test_user.id, "analysis")
        assert perm.allowed is False

    async def test_list_allowed_page_keys(self, db: AsyncSession, test_user):
        await set_user_page_permission(db, test_user.id, "analysis", True)
        await set_user_page_permission(db, test_user.id, "trading", True)
        await set_user_page_permission(db, test_user.id, "settings", False)

        allowed = await list_allowed_page_keys(db, test_user.id)
        assert "analysis" in allowed
        assert "trading" in allowed
        assert "settings" not in allowed

    async def test_get_user_page_permissions_map(self, db: AsyncSession, test_user):
        await set_user_page_permission(db, test_user.id, "analysis", True)
        await set_user_page_permission(db, test_user.id, "trading", False)

        mapping = await get_user_page_permissions_map(db, test_user.id)
        assert mapping.get("analysis") is True
        assert mapping.get("trading") is False

    async def test_set_user_setting_permission(self, db: AsyncSession, test_user):
        await set_user_setting_permission(db, test_user.id, "llm", True)

        perm = await get_user_setting_permission(db, test_user.id, "llm")
        assert perm is not None
        assert perm.allowed is True

    async def test_list_allowed_setting_sections(self, db: AsyncSession, test_user):
        await set_user_setting_permission(db, test_user.id, "general", True)
        await set_user_setting_permission(db, test_user.id, "llm", True)
        await set_user_setting_permission(db, test_user.id, "risk", False)

        allowed = await list_allowed_setting_sections(db, test_user.id)
        assert "general" in allowed
        assert "llm" in allowed
        assert "risk" not in allowed

    async def test_get_user_setting_permissions_map(self, db: AsyncSession, test_user):
        await set_user_setting_permission(db, test_user.id, "general", True)
        await set_user_setting_permission(db, test_user.id, "webhooks", False)

        mapping = await get_user_setting_permissions_map(db, test_user.id)
        assert mapping.get("general") is True
        assert mapping.get("webhooks") is False

    async def test_set_user_page_permission_isolation(self, db: AsyncSession, test_user):
        await set_user_page_permission(db, test_user.id, "analysis", True)

        perm = await get_user_page_permission(db, 99999, "analysis")
        assert perm is None