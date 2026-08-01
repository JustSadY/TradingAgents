from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories.assistant import add_message, clear_messages, get_messages

class TestAssistantRepository:
    async def test_add_message(self, db: AsyncSession, test_user: User):
        msg = await add_message(db, user_id=test_user.id, role="user", content="Hello assistant")
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Hello assistant"
        assert msg.user_id == test_user.id

    async def test_get_messages(self, db: AsyncSession, test_user: User):
        await add_message(db, test_user.id, "user", "First message")
        await add_message(db, test_user.id, "user", "Second message")

        messages = await get_messages(db, test_user.id)
        assert len(messages) == 2

    async def test_get_messages_ordered(self, db: AsyncSession, test_user: User):
        await add_message(db, test_user.id, "user", "First")
        await add_message(db, test_user.id, "assistant", "Response")

        messages = await get_messages(db, test_user.id)
        assert messages[0].role == "user"
        assert messages[0].content == "First"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Response"

    async def test_get_messages_scoped_by_user(self, db: AsyncSession, test_user: User, admin_user: User):
        await add_message(db, test_user.id, "user", "Test message")

        user_msgs = await get_messages(db, test_user.id)
        assert len(user_msgs) == 1

        admin_msgs = await get_messages(db, admin_user.id)
        assert len(admin_msgs) == 0

    async def test_clear_messages(self, db: AsyncSession, test_user: User):
        await add_message(db, test_user.id, "user", "Message 1")
        await add_message(db, test_user.id, "user", "Message 2")
        await clear_messages(db, test_user.id)

        messages = await get_messages(db, test_user.id)
        assert len(messages) == 0
