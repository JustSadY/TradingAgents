"""Process-wide Redis client management (opt-in).

Redis is enabled by setting ``REDIS_URL`` in ``.env``. When it is unset every
consumer falls back to the original single-process in-memory behaviour, so a
plain single-uvicorn deployment keeps working with zero new infrastructure.

When enabled, Redis carries:
- analysis WebSocket events (pub/sub fan-out across web/worker processes)
- the analysis task registry + ownership map (cross-process visibility)
- cancel requests (control channel observed by every process)
- the arq job queue (when ``ANALYSIS_QUEUE_MODE=worker``)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from backend.core.config import get_settings

_logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "analysis:events"
CONTROL_CHANNEL = "analysis:control"

_client = None


def redis_enabled() -> bool:
    return bool(get_settings().REDIS_URL)


def get_redis():
    """Return the shared async Redis client (or ``None`` when disabled)."""
    global _client
    if not redis_enabled():
        return None
    if _client is None:
        import redis.asyncio as redis

        _client = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
        _logger.info("Redis connected: %s", get_settings().REDIS_URL.split("@")[-1])
    return _client


def set_redis_for_testing(client) -> None:
    """Inject a fake client in tests (bypasses REDIS_URL)."""
    global _client
    _client = client


async def subscribe_loop(
    channel: str,
    handler: Callable[[dict], Awaitable[None]],
    *,
    name: str,
) -> None:
    """Long-lived consumer for a Redis pub/sub ``channel``.

    Decodes each message's JSON payload and dispatches it to ``handler``. Exits
    quietly when Redis is disabled (returns) and re-raises on cancellation;
    reconnects with a 2s backoff on transport errors and drops an individual
    malformed message without tearing down the subscription. ``name`` is used
    only for log context.
    """
    while True:
        try:
            redis = get_redis()
            if redis is None:
                return
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    await handler(json.loads(message["data"]))
                except Exception as exc:  # noqa: BLE001 — one bad message must not kill the loop
                    _logger.warning("%s: dropped malformed message: %s", name, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — reconnect on any transport error
            _logger.warning("%s disconnected (%s); retrying in 2s", name, exc)
            await asyncio.sleep(2)


async def close_pool_or_client(connection, logger, label: str) -> None:
    if connection is not None:
        try:
            await connection.aclose()
        except Exception as exc:
            logger.debug("%s close failed: %s", label, exc)


async def close_redis() -> None:
    global _client
    if _client is not None:
        await close_pool_or_client(_client, _logger, "Redis")
        _client = None
