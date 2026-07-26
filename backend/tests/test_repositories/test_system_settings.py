from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.system_settings import (
    create_system_settings,
    get_system_settings_by_id,
    update_system_settings_fields,
)


class TestSystemSettingsRepository:
    async def test_create_system_settings(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        assert ss is not None
        assert ss.id == 1

    async def test_get_system_settings_by_id(self, db: AsyncSession):
        await create_system_settings(db, ss_id=1)
        found = await get_system_settings_by_id(db, 1)
        assert found is not None
        assert found.id == 1

    async def test_get_system_settings_nonexistent(self, db: AsyncSession):
        found = await get_system_settings_by_id(db, 999)
        assert found is None

    async def test_update_system_settings_fields(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        updated = await update_system_settings_fields(
            db, ss,
            openai_api_key="sk-test",
            anthropic_api_key="ant-test",
        )
        assert updated.openai_api_key == "sk-test"
        assert updated.anthropic_api_key == "ant-test"

    async def test_update_partial_fields(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        await update_system_settings_fields(db, ss, openai_api_key="sk-test")
        assert ss.openai_api_key == "sk-test"
        assert ss.anthropic_api_key is None

    async def test_create_then_get_returns_same(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        await update_system_settings_fields(db, ss, openai_api_key="sk-123")
        found = await get_system_settings_by_id(db, 1)
        assert found.openai_api_key == "sk-123"

    async def test_get_system_settings_default_id(self, db: AsyncSession):
        ss = await create_system_settings(db)
        assert ss.id == 1