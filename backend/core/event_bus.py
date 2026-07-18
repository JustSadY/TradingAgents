"""Analysis event distribution: direct in-process or via Redis pub/sub.

``publish_event``/``publish_close`` are the single write path for analysis
WebSocket events. Without Redis they call the local ``ws_manager`` directly
(original behaviour). With Redis they PUBLISH to ``analysis:events``; every
web process runs ``event_forwarder`` which delivers received events to its
local ``ws_manager`` so clients connected to any process see the stream —
including runs executed in a separate arq worker process.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.core.redis_bus import EVENTS_CHANNEL, get_redis, redis_enabled, subscribe_loop
from backend.core.websocket import ws_manager

_logger = logging.getLogger(__name__)

_CLOSE_TYPE = "__task_close__"


async def publish_event(task_id: str, event: dict[str, Any]) -> None:
    if redis_enabled():
        redis = get_redis()
        await redis.publish(EVENTS_CHANNEL, json.dumps({"task_id": task_id, "event": event}, ensure_ascii=False))
        return
    await ws_manager.send(task_id, event)


async def publish_close(task_id: str) -> None:
    if redis_enabled():
        redis = get_redis()
        await redis.publish(EVENTS_CHANNEL, json.dumps({"task_id": task_id, "event": {"type": _CLOSE_TYPE}}))
        return
    await ws_manager.close_task(task_id)


async def _deliver(task_id: str, event: dict[str, Any]) -> None:
    if event.get("type") == _CLOSE_TYPE:
        await ws_manager.close_task(task_id)
    else:
        await ws_manager.send(task_id, event)


async def event_forwarder() -> None:
    """Deliver Redis-published analysis events to this process's ws_manager.

    Runs as a long-lived background task in each web process while Redis is
    enabled; see ``redis_bus.subscribe_loop`` for reconnect/error semantics.
    """

    async def deliver(payload: dict) -> None:
        await _deliver(payload["task_id"], payload["event"])

    await subscribe_loop(EVENTS_CHANNEL, deliver, name="Event forwarder")
