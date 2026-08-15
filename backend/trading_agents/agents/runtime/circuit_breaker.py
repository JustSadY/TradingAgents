"""Circuit-breaker state for graph nodes, shared across workers when possible.

The state used to be a module-level dict, so in worker mode every worker had to
rediscover a failing provider on its own: with N workers a provider outage cost
N x threshold calls before anything opened. Backing it with Redis — which the
app already runs for the event bus and task registry in worker mode — makes one
worker's observation close the circuit for all of them.

Redis is optional. Without ``REDIS_URL`` the in-memory implementation is used
unchanged, which is what single-node deployments and the test suite get.
"""

from __future__ import annotations

import logging
import time

_logger = logging.getLogger(__name__)

_KEY_PREFIX = "circuit:"

# Fallback store, and the only store when Redis is disabled.
_local: dict[str, dict] = {}


def _redis():
    """Return the shared client, or ``None`` when Redis is not configured."""
    from backend.core.redis_bus import get_redis

    return get_redis()


def _closed() -> dict:
    return {"failures": 0, "open_since": None}


async def get_state(key: str) -> dict:
    """Return ``{"failures": int, "open_since": float | None}`` for *key*."""
    client = _redis()
    if client is None:
        return dict(_local.get(key) or _closed())

    try:
        raw = await client.hgetall(f"{_KEY_PREFIX}{key}")
    except Exception as exc:
        # A breaker that cannot read its own state must not take the node down;
        # fall back to the local view rather than failing the analysis.
        _logger.warning("Circuit state read failed for %s, using local state: %s", key, exc)
        return dict(_local.get(key) or _closed())

    if not raw:
        return _closed()
    open_since = raw.get("open_since")
    return {
        "failures": int(raw.get("failures") or 0),
        "open_since": float(open_since) if open_since not in (None, "", "none") else None,
    }


async def record_failure(key: str, threshold: int, cooldown: int) -> dict:
    """Count a failure and open the circuit once *threshold* is reached."""
    client = _redis()
    if client is None:
        entry = _local.setdefault(key, _closed())
        entry["failures"] += 1
        if entry["failures"] >= threshold:
            entry["open_since"] = time.time()
        return dict(entry)

    name = f"{_KEY_PREFIX}{key}"
    try:
        failures = int(await client.hincrby(name, "failures", 1))
        opened_at = None
        if failures >= threshold:
            opened_at = time.time()
            await client.hset(name, "open_since", opened_at)
        # Expire well after the cooldown so a quiet circuit cleans itself up
        # instead of pinning a failure count forever.
        await client.expire(name, max(cooldown * 10, 600))
        return {"failures": failures, "open_since": opened_at}
    except Exception as exc:
        _logger.warning("Circuit state write failed for %s, using local state: %s", key, exc)
        entry = _local.setdefault(key, _closed())
        entry["failures"] += 1
        if entry["failures"] >= threshold:
            entry["open_since"] = time.time()
        return dict(entry)


async def reset(key: str) -> None:
    """Close the circuit after a success or once the cooldown has elapsed."""
    _local.pop(key, None)
    client = _redis()
    if client is None:
        return
    try:
        await client.delete(f"{_KEY_PREFIX}{key}")
    except Exception as exc:
        _logger.warning("Circuit state reset failed for %s: %s", key, exc)


def reset_all_local() -> None:
    """Clear the in-memory store (tests only)."""
    _local.clear()
