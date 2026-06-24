"""Tests for the opt-in Redis scaling layer (event bus + task store).

Uses an in-memory fake Redis client so no server is needed. The
``redis_enabled`` switch is monkeypatched per test to exercise both the
disabled (in-process) and enabled (pub/sub) code paths.
"""

import json

import pytest

from backend.core import event_bus, task_store


class FakeRedis:
    """Minimal async Redis stand-in covering the commands the layer uses."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set] = {}
        self.published: list[tuple[str, str]] = []

    async def set(self, key, value, ex=None):
        self.kv[key] = value

    async def get(self, key):
        return self.kv.get(key)

    async def delete(self, key):
        self.kv.pop(key, None)

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key, member):
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    async def expire(self, key, ttl):
        pass

    async def publish(self, channel, message):
        self.published.append((channel, message))


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    for module in (event_bus, task_store):
        monkeypatch.setattr(module, "redis_enabled", lambda: True)
        monkeypatch.setattr(module, "get_redis", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


async def test_publish_event_without_redis_goes_to_local_ws(monkeypatch):
    sent = []

    async def fake_send(task_id, event):
        sent.append((task_id, event))

    monkeypatch.setattr(event_bus, "redis_enabled", lambda: False)
    monkeypatch.setattr(event_bus.ws_manager, "send", fake_send)

    await event_bus.publish_event("t-1", {"type": "report"})
    assert sent == [("t-1", {"type": "report"})]


async def test_publish_event_with_redis_publishes_to_channel(fake_redis):
    await event_bus.publish_event("t-1", {"type": "report", "section": "market_report"})

    ((channel, raw),) = fake_redis.published
    assert channel == event_bus.EVENTS_CHANNEL
    payload = json.loads(raw)
    assert payload["task_id"] == "t-1"
    assert payload["event"]["type"] == "report"


async def test_close_routes_to_close_task_via_deliver(fake_redis, monkeypatch):
    closed = []

    async def fake_close(task_id):
        closed.append(task_id)

    monkeypatch.setattr(event_bus.ws_manager, "close_task", fake_close)

    await event_bus.publish_close("t-9")
    ((_, raw),) = fake_redis.published
    payload = json.loads(raw)
    # Replaying the published message through the forwarder's delivery hook
    # must translate the close marker into a local close_task call.
    await event_bus._deliver(payload["task_id"], payload["event"])
    assert closed == ["t-9"]


# ---------------------------------------------------------------------------
# Task store
# ---------------------------------------------------------------------------


async def test_task_store_noops_when_redis_disabled(monkeypatch):
    monkeypatch.setattr(task_store, "redis_enabled", lambda: False)
    await task_store.set_owner("t-1", 5)
    assert await task_store.get_owner("t-1") is None
    assert await task_store.list_tasks_for_user(5) == []


async def test_owner_round_trip_and_system_runs(fake_redis):
    await task_store.set_owner("t-1", 5)
    assert await task_store.get_owner("t-1") == 5

    # System-triggered runs store an empty owner that must not be claimable.
    await task_store.set_owner("t-sys", None)
    assert await task_store.get_owner("t-sys") is None

    await task_store.clear_owner("t-1")
    assert await task_store.get_owner("t-1") is None


async def test_meta_listing_per_user_and_stale_cleanup(fake_redis):
    await task_store.set_meta("t-1", {"ticker": "AAPL", "user_id": 5})
    await task_store.set_meta("t-2", {"ticker": "MSFT", "user_id": 6})

    tasks = await task_store.list_tasks_for_user(5)
    assert [t["ticker"] for t in tasks] == ["AAPL"]

    # Simulate an expired meta entry whose index entry lingers.
    fake_redis.kv.pop("analysis:meta:t-1")
    assert await task_store.list_tasks_for_user(5) == []
    assert "t-1" not in fake_redis.sets.get("analysis:user_tasks:5", set())


async def test_publish_cancel_emits_control_message(fake_redis):
    await task_store.publish_cancel("t-1")
    ((channel, raw),) = fake_redis.published
    assert channel == task_store.CONTROL_CHANNEL
    assert json.loads(raw) == {"action": "cancel", "task_id": "t-1"}


# ---------------------------------------------------------------------------
# analysis_service integration with the store
# ---------------------------------------------------------------------------


async def test_is_task_owner_falls_back_to_redis(fake_redis):
    from backend.services import analysis_service as svc

    # Owner registered by another process: present in Redis, absent locally.
    await task_store.set_owner("remote-task", 7)
    assert await svc.is_task_owner("remote-task", 7) is True
    assert await svc.is_task_owner("remote-task", 8) is False


async def test_active_tasks_merge_local_and_remote(fake_redis):
    from backend.services import analysis_service as svc

    svc._TASK_REGISTRY["local-1"] = {"ticker": "AAPL", "user_id": 5}
    try:
        await task_store.set_meta("remote-1", {"ticker": "MSFT", "user_id": 5})
        # A duplicate of the local task in Redis must not be listed twice.
        await task_store.set_meta("local-1", {"ticker": "AAPL", "user_id": 5})

        tasks = await svc.get_active_tasks_for_user(5)
        assert sorted(t["task_id"] for t in tasks) == ["local-1", "remote-1"]
    finally:
        svc._TASK_REGISTRY.pop("local-1", None)


async def test_cancel_unknown_task_broadcasts_control_message(fake_redis):
    from backend.services import analysis_service as svc

    cancelled = await svc.cancel_analysis("running-elsewhere")
    assert cancelled is False
    assert any(ch == task_store.CONTROL_CHANNEL for ch, _ in fake_redis.published)


def test_inline_queue_mode_is_default():
    from backend.services.analysis_queue import queue_mode

    assert queue_mode() == "inline"


def test_worker_mode_requires_redis_url():
    from backend.core.config import Settings

    with pytest.raises(ValueError, match="requires REDIS_URL"):
        Settings(ANALYSIS_QUEUE_MODE="worker", REDIS_URL="", _env_file=None)


def test_invalid_queue_mode_rejected():
    from backend.core.config import Settings

    with pytest.raises(ValueError, match="inline.*or.*worker"):
        Settings(ANALYSIS_QUEUE_MODE="bogus", _env_file=None)
