from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.preset import create_preset, get_preset_by_id, get_preset_by_name, list_presets

class TestPresetRepository:
    async def test_create_preset(self, db: AsyncSession, test_user):
        preset = await create_preset(
            db,
            user_id=test_user.id,
            name="My Preset",
            description="A test preset",
            settings_json='{"llm_provider": "openai"}',
        )
        assert preset.id is not None
        assert preset.name == "My Preset"
        assert preset.user_id == test_user.id

    async def test_list_presets(self, db: AsyncSession, test_user):
        await create_preset(db, user_id=test_user.id, name="Preset A", description="", settings_json="{}")
        await create_preset(db, user_id=test_user.id, name="Preset B", description="", settings_json="{}")

        presets = await list_presets(db, user=test_user)
        assert len(presets) == 2

    async def test_list_presets_scoped(self, db: AsyncSession, test_user):
        await create_preset(db, user_id=test_user.id, name="Mine", description="", settings_json="{}")

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        presets = await list_presets(db, user=other_user)
        assert len(presets) == 0

    async def test_list_presets_admin_sees_all(self, db: AsyncSession, test_user, admin_user):
        await create_preset(db, user_id=test_user.id, name="Mine", description="", settings_json="{}")

        presets = await list_presets(db, user=admin_user)
        assert len(presets) == 1

    async def test_get_preset_by_id(self, db: AsyncSession, test_user):
        preset = await create_preset(db, user_id=test_user.id, name="Preset", description="", settings_json="{}")

        found = await get_preset_by_id(db, preset.id, user=test_user)
        assert found is not None
        assert found.name == "Preset"

    async def test_get_preset_by_id_scoped(self, db: AsyncSession, test_user):
        preset = await create_preset(db, user_id=test_user.id, name="Mine", description="", settings_json="{}")

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        found = await get_preset_by_id(db, preset.id, user=other_user)
        assert found is None

    async def test_get_preset_by_name(self, db: AsyncSession, test_user):
        await create_preset(db, user_id=test_user.id, name="My Preset", description="", settings_json="{}")

        found = await get_preset_by_name(db, "My Preset", test_user.id)
        assert found is not None
        assert found.description == ""

    async def test_get_preset_by_name_wrong_user(self, db: AsyncSession, test_user):
        await create_preset(db, user_id=test_user.id, name="Mine", description="", settings_json="{}")

        found = await get_preset_by_name(db, "Mine", 99999)
        assert found is None

    async def test_get_preset_by_name_nonexistent(self, db: AsyncSession, test_user):
        found = await get_preset_by_name(db, "NonExistent", test_user.id)
        assert found is None
