from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.persona import (
    create_user_persona,
    delete_user_persona,
    get_user_persona_by_key,
    list_user_personas,
    update_user_persona,
)


class TestPersonaRepository:
    async def test_create_user_persona(self, db: AsyncSession, test_user):
        persona = await create_user_persona(
            db,
            user_id=test_user.id,
            key="conservative",
            label="Conservative",
            description="Low risk tolerance",
            instructions="Be careful",
        )
        assert persona.id is not None
        assert persona.key == "conservative"
        assert persona.label == "Conservative"
        assert persona.user_id == test_user.id

    async def test_list_user_personas(self, db: AsyncSession, test_user):
        await create_user_persona(db, user_id=test_user.id, key="p1", label="P1", description="", instructions="")
        await create_user_persona(db, user_id=test_user.id, key="p2", label="P2", description="", instructions="")

        personas = await list_user_personas(db, test_user.id)
        assert len(personas) == 2

    async def test_list_user_personas_scoped(self, db: AsyncSession, test_user):
        await create_user_persona(db, user_id=test_user.id, key="p1", label="P1", description="", instructions="")

        other_personas = await list_user_personas(db, 99999)
        assert len(other_personas) == 0

    async def test_get_user_persona_by_key(self, db: AsyncSession, test_user):
        await create_user_persona(
            db,
            user_id=test_user.id,
            key="aggressive",
            label="Aggressive",
            description="High risk",
            instructions="Take risks",
        )

        found = await get_user_persona_by_key(db, test_user.id, "aggressive")
        assert found is not None
        assert found.label == "Aggressive"
        assert found.instructions == "Take risks"

    async def test_get_user_persona_by_key_wrong_user(self, db: AsyncSession, test_user):
        await create_user_persona(
            db, user_id=test_user.id, key="aggressive", label="Aggressive", description="", instructions=""
        )

        found = await get_user_persona_by_key(db, 99999, "aggressive")
        assert found is None

    async def test_get_user_persona_by_key_nonexistent(self, db: AsyncSession, test_user):
        found = await get_user_persona_by_key(db, test_user.id, "nonexistent")
        assert found is None

    async def test_update_user_persona(self, db: AsyncSession, test_user):
        persona = await create_user_persona(
            db,
            user_id=test_user.id,
            key="balanced",
            label="Balanced",
            description="Middle ground",
            instructions="Be balanced",
        )

        updated = await update_user_persona(
            db,
            persona,
            label="Moderate",
            description="Updated description",
            instructions="Be moderate",
        )
        assert updated.label == "Moderate"
        assert updated.description == "Updated description"
        assert updated.instructions == "Be moderate"

    async def test_delete_user_persona(self, db: AsyncSession, test_user):
        persona = await create_user_persona(
            db, user_id=test_user.id, key="temp", label="Temp", description="", instructions=""
        )

        await delete_user_persona(db, persona)

        found = await get_user_persona_by_key(db, test_user.id, "temp")
        assert found is None
