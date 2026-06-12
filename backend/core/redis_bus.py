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

import logging

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


async def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception as exc:  # noqa: BLE001 — best-effort shutdown
            _logger.debug("Redis close failed: %s", exc)
        _client = None
