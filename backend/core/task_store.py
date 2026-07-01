"""Cross-process analysis task registry and ownership map (Redis-backed).

Every function is a no-op / empty result when Redis is disabled; callers in
``analysis_service`` keep their in-memory dicts as the first source of truth
and use this store to extend visibility across web and worker processes.

Keys (all with a sliding TTL so crashed processes cannot leak entries):
- ``analysis:owner:{task_id}``  -> user id ("" for system-triggered runs)
- ``analysis:meta:{task_id}``   -> JSON task metadata for the active-task list
- ``analysis:user_tasks:{uid}`` -> set of that user's active task ids
"""

from __future__ import annotations

import json
import logging

from backend.core.redis_bus import CONTROL_CHANNEL, get_redis, redis_enabled, subscribe_loop

_logger = logging.getLogger(__name__)

# Analyses run minutes; entries outliving this are leftovers from a crash.
_TTL_SECONDS = 2 * 60 * 60


def _owner_key(task_id: str) -> str:
    return f"analysis:owner:{task_id}"


def _meta_key(task_id: str) -> str:
    return f"analysis:meta:{task_id}"


def _user_tasks_key(user_id: int) -> str:
    return f"analysis:user_tasks:{user_id}"


async def set_owner(task_id: str, user_id: int | None) -> None:
    if not redis_enabled():
        return
    await get_redis().set(_owner_key(task_id), "" if user_id is None else str(user_id), ex=_TTL_SECONDS)


async def get_owner(task_id: str) -> int | None:
    """Owner user id, or ``None`` when unknown or system-owned."""
    if not redis_enabled():
        return None
    raw = await get_redis().get(_owner_key(task_id))
    return int(raw) if raw else None


async def clear_owner(task_id: str) -> None:
    if not redis_enabled():
        return
    await get_redis().delete(_owner_key(task_id))


async def set_meta(task_id: str, meta: dict) -> None:
    if not redis_enabled():
        return
    redis = get_redis()
    await redis.set(_meta_key(task_id), json.dumps(meta), ex=_TTL_SECONDS)
    user_id = meta.get("user_id")
    if user_id is not None:
        key = _user_tasks_key(user_id)
        await redis.sadd(key, task_id)
        await redis.expire(key, _TTL_SECONDS)


async def clear_meta(task_id: str, user_id: int | None = None) -> None:
    if not redis_enabled():
        return
    redis = get_redis()
    await redis.delete(_meta_key(task_id))
    if user_id is not None:
        await redis.srem(_user_tasks_key(user_id), task_id)


async def list_tasks_for_user(user_id: int) -> list[dict]:
    """Active tasks for ``user_id`` as ``{"task_id": ..., **meta}`` dicts."""
    if not redis_enabled():
        return []
    redis = get_redis()
    task_ids = await redis.smembers(_user_tasks_key(user_id))
    tasks: list[dict] = []
    for task_id in task_ids:
        raw = await redis.get(_meta_key(task_id))
        if raw is None:
            # Meta expired or cleaned up; drop the stale index entry.
            await redis.srem(_user_tasks_key(user_id), task_id)
            continue
        try:
            tasks.append({"task_id": task_id, **json.loads(raw)})
        except (TypeError, ValueError):
            continue
    return tasks


async def publish_cancel(task_id: str) -> None:
    """Ask whichever process is running ``task_id`` to cancel it."""
    if not redis_enabled():
        return
    await get_redis().publish(CONTROL_CHANNEL, json.dumps({"action": "cancel", "task_id": task_id}))


async def control_listener(cancel_local) -> None:
    """Listen for control messages and apply them to this process.

    ``cancel_local`` is an async callable ``(task_id) -> bool`` that cancels a
    task if it runs in the current process. Runs in web and worker processes.
    """
    async def handle(payload: dict) -> None:
        if payload.get("action") == "cancel" and payload.get("task_id"):
            await cancel_local(payload["task_id"])

    await subscribe_loop(CONTROL_CHANNEL, handle, name="Control listener")
