from __future__ import annotations

import json

import pytest

from backend.core import event_bus

class _FakeRedis:
    def __init__(self):
        self.payloads: list[str] = []

    async def publish(self, _channel: str, payload: str) -> None:
        self.payloads.append(payload)

@pytest.mark.asyncio
async def test_redis_published_event_reaches_publisher_process(monkeypatch):
    """The Redis forwarder must not dedupe the publisher's own event first."""
    fake_redis = _FakeRedis()
    delivered: list[tuple[str, dict]] = []

    event_bus._dedup = event_bus._DedupTracker()
    event_bus._seq_counters.clear()
    monkeypatch.setattr(event_bus, "redis_enabled", lambda: True)
    monkeypatch.setattr(event_bus, "get_redis", lambda: fake_redis)

    async def fake_send(task_id: str, event: dict) -> None:
        delivered.append((task_id, event))

    async def fake_subscribe(_channel: str, callback, *, name: str) -> None:
        assert name == "Event forwarder"
        await callback(json.loads(fake_redis.payloads[0]))

    monkeypatch.setattr(event_bus.ws_manager, "send", fake_send)
    monkeypatch.setattr(event_bus, "subscribe_loop", fake_subscribe)

    await event_bus.publish_event("task-1", {"type": "status", "status": "running"})
    await event_bus.event_forwarder()

    assert delivered == [("task-1", {"type": "status", "status": "running"})]
