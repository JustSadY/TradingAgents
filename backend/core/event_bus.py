"""Analysis event distribution: direct in-process or via Redis pub/sub.

``publish_event``/``publish_close`` are the single write path for analysis
WebSocket events. Without Redis they call the local ``ws_manager`` directly
(original behaviour). With Redis they PUBLISH to ``analysis:events``; every
web process runs ``event_forwarder`` which delivers received events to its
local ``ws_manager`` so clients connected to any process see the stream —
including runs executed in a separate arq worker process.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from backend.core.redis_bus import EVENTS_CHANNEL, get_redis, redis_enabled
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
    """Subscribe to the events channel and feed the local WebSocket manager.

    Runs as a long-lived background task in each web process while Redis is
    enabled. Reconnects with backoff if the subscription drops.
    """
    while True:
        try:
            redis = get_redis()
            if redis is None:
                return
            pubsub = redis.pubsub()
            await pubsub.subscribe(EVENTS_CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    await _deliver(payload["task_id"], payload["event"])
                except Exception as exc:  # noqa: BLE001 — one bad event must not kill the stream
                    _logger.warning("Dropped malformed analysis event: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — reconnect on any transport error
            _logger.warning("Event forwarder disconnected (%s); retrying in 2s", exc)
            await asyncio.sleep(2)
