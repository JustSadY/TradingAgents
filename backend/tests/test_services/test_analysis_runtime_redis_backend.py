from __future__ import annotations

from backend.analysis_runtime.redis_backend import RedisBackend


async def test_invalid_runtime_metadata_is_non_fatal(monkeypatch):
    from backend.analysis_runtime import redis_backend

    async def invalid_meta(_task_id: str):
        return {
            "ticker": "NVDA",
            "trade_date": "2026-08-17",
            "asset_type": "stock",
            "user_id": 7,
            "status": "not-a-status",
            "started_at": 1.0,
        }

    monkeypatch.setattr(redis_backend.task_store, "get_meta", invalid_meta)

    assert await RedisBackend().metadata("stale-task") is None


async def test_active_tasks_skip_only_invalid_runtime_rows(monkeypatch):
    from backend.analysis_runtime import redis_backend

    async def rows(_user_id: int):
        return [
            {
                "task_id": "valid-task",
                "ticker": "AAPL",
                "trade_date": "2026-08-17",
                "asset_type": "stock",
                "user_id": 3,
                "status": "running",
                "started_at": 42.0,
            },
            {
                "task_id": "invalid-task",
                "ticker": "MSFT",
                "trade_date": "2026-08-17",
                "asset_type": "stock",
                "user_id": 3,
                "status": "broken",
                "started_at": 43.0,
            },
            {
                "ticker": "NO-ID",
                "trade_date": "2026-08-17",
                "asset_type": "stock",
                "user_id": 3,
                "status": "running",
                "started_at": 44.0,
            },
        ]

    monkeypatch.setattr(redis_backend.task_store, "list_tasks_for_user", rows)

    tasks = await RedisBackend().active_tasks(3)

    assert [task.task_id for task in tasks] == ["valid-task"]
