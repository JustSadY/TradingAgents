from redis.exceptions import ConnectionError

from backend.core import task_store


class _UnavailableRedis:
    async def smembers(self, _key):
        raise ConnectionError("Redis is offline")


async def test_task_listing_falls_back_to_empty_when_configured_redis_is_offline(monkeypatch):
    """The active-analysis endpoint must not become a 500 when Redis is down."""
    monkeypatch.setattr(task_store, "redis_enabled", lambda: True)
    monkeypatch.setattr(task_store, "get_redis", lambda: _UnavailableRedis())

    assert await task_store.list_tasks_for_user(42) == []
