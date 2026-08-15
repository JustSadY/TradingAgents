from __future__ import annotations

import pytest
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
            db,
            ss,
            active_data_vendor="alpha_vantage",
            data_vendor_news="finnhub",
        )
        assert updated.active_data_vendor == "alpha_vantage"
        assert updated.data_vendor_news == "finnhub"

    async def test_update_partial_fields(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        await update_system_settings_fields(db, ss, active_data_vendor="alpha_vantage")
        assert ss.active_data_vendor == "alpha_vantage"
        assert ss.active_broker == "simulation"

    async def test_update_rejects_unknown_fields(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        with pytest.raises(ValueError, match="Unknown system-settings fields"):
            await update_system_settings_fields(db, ss, openai_api_key="sk-test")

    async def test_create_then_get_returns_same(self, db: AsyncSession):
        ss = await create_system_settings(db, ss_id=1)
        await update_system_settings_fields(db, ss, active_data_vendor="alpha_vantage")
        found = await get_system_settings_by_id(db, 1)
        assert found.active_data_vendor == "alpha_vantage"

    async def test_get_system_settings_default_id(self, db: AsyncSession):
        ss = await create_system_settings(db)
        assert ss.id == 1
