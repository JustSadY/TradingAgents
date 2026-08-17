from __future__ import annotations

from collections.abc import Awaitable, Callable


def enabled() -> bool:
    """Return whether the shared Redis-backed analysis transport is enabled."""
    from backend.core.redis_bus import redis_enabled

    return redis_enabled()


async def forward_events() -> None:
    """Forward distributed analysis events to sockets in this web process."""
    from backend.core.event_bus import event_forwarder

    await event_forwarder()


async def listen_for_controls(cancel_local: Callable[[str], Awaitable[bool]]) -> None:
    """Apply distributed analysis control messages to tasks in this process."""
    from backend.core.task_store import control_listener

    await control_listener(cancel_local)


async def close() -> None:
    """Close the shared analysis Redis connection during process shutdown."""
    from backend.core.redis_bus import close_redis

    await close_redis()
