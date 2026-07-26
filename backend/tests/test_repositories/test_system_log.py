from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.log import SystemLog
from backend.repositories.system_log import list_all_logs, list_user_logs


class TestSystemLogRepository:
    async def _create_log(
        self,
        db: AsyncSession,
        user_id: int | None = None,
        level: str = "INFO",
        source: str = "test",
        message: str = "Test log entry",
    ) -> SystemLog:
        log = SystemLog(
            level=level,
            source=source,
            message=message,
            user_id=user_id,
        )
        db.add(log)
        await db.flush()
        return log

    async def test_list_user_logs(self, db: AsyncSession, test_user):
        await self._create_log(db, user_id=test_user.id, message="Entry 1")
        await self._create_log(db, user_id=test_user.id, message="Entry 2")

        logs = await list_user_logs(db, user=test_user)
        assert len(logs) == 2

    async def test_list_user_logs_scoped(self, db: AsyncSession, test_user):
        await self._create_log(db, user_id=test_user.id, message="Mine")

        other_user = type("FakeUser", (), {"id": 999, "is_admin": False})()
        logs = await list_user_logs(db, user=other_user)
        assert len(logs) == 0

    async def test_list_user_logs_admin_sees_all(self, db: AsyncSession, test_user, admin_user):
        await self._create_log(db, user_id=test_user.id, message="User's log")

        logs = await list_user_logs(db, user=admin_user)
        assert len(logs) == 1

    async def test_list_user_logs_filter_by_level(self, db: AsyncSession, test_user):
        await self._create_log(db, user_id=test_user.id, level="INFO")
        await self._create_log(db, user_id=test_user.id, level="WARNING")
        await self._create_log(db, user_id=test_user.id, level="ERROR")

        info_logs = await list_user_logs(db, user=test_user, level="info")
        assert len(info_logs) == 1
        assert info_logs[0].level == "INFO"

        error_logs = await list_user_logs(db, user=test_user, level="ERROR")
        assert len(error_logs) == 1
        assert error_logs[0].level == "ERROR"

    async def test_list_user_logs_limit(self, db: AsyncSession, test_user):
        for i in range(5):
            await self._create_log(db, user_id=test_user.id, message=f"Entry {i}")

        logs = await list_user_logs(db, user=test_user, limit=3)
        assert len(logs) == 3

    async def test_list_user_logs_offset(self, db: AsyncSession, test_user):
        for i in range(5):
            await self._create_log(db, user_id=test_user.id, message=f"Entry {i}")

        all_logs = await list_user_logs(db, user=test_user)
        assert len(all_logs) == 5

        offset_logs = await list_user_logs(db, user=test_user, offset=3)
        assert len(offset_logs) == 2

    async def test_list_user_logs_empty(self, db: AsyncSession, test_user):
        logs = await list_user_logs(db, user=test_user)
        assert len(logs) == 0

    async def test_list_all_logs(self, db: AsyncSession, test_user, admin_user):
        await self._create_log(db, user_id=test_user.id, message="Entry 1")
        await self._create_log(db, user_id=admin_user.id, message="Entry 2")

        logs = await list_all_logs(db)
        assert len(logs) == 2

    async def test_list_all_logs_filter_level(self, db: AsyncSession, test_user):
        await self._create_log(db, user_id=test_user.id, level="ERROR", message="Error 1")
        await self._create_log(db, user_id=test_user.id, level="INFO", message="Info 1")

        error_logs = await list_all_logs(db, level="ERROR")
        assert len(error_logs) == 1
        assert error_logs[0].message == "Error 1"

    async def test_list_all_logs_filter_source(self, db: AsyncSession, test_user):
        await self._create_log(db, user_id=test_user.id, source="auth", message="Auth log")
        await self._create_log(db, user_id=test_user.id, source="api", message="API log")

        api_logs = await list_all_logs(db, source="api")
        assert len(api_logs) == 1
        assert api_logs[0].source == "api"

    async def test_list_all_logs_filter_user_id(self, db: AsyncSession, test_user, admin_user):
        await self._create_log(db, user_id=test_user.id, message="User log")
        await self._create_log(db, user_id=admin_user.id, message="Other log")

        user_logs = await list_all_logs(db, user_id=test_user.id)
        assert len(user_logs) == 1
        assert user_logs[0].message == "User log"
