"""Cross-process analysis task registry and ownership map (Redis-backed).

Every function is a no-op / empty result when Redis is disabled; callers in
``analysis_service`` keep their in-memory dicts as the first source of truth
and use this store to extend visibility across web and worker processes.

Keys (all with a sliding TTL so crashed processes cannot leak entries):
- ``analysis:owner:{task_id}``  -> user id ("" for system-triggered runs)
- ``analysis:meta:{task_id}``   -> JSON task metadata for the active-task list
- ``analysis:user_tasks:{uid}`` -> set of that user's active task ids
- ``analysis:cancel:{task_id}`` -> durable cancellation intent for queued runs
"""

from __future__ import annotations

import json
import logging

from redis.exceptions import RedisError

from backend.core.redis_bus import CONTROL_CHANNEL, get_redis, redis_enabled, subscribe_loop

_logger = logging.getLogger(__name__)

_TTL_SECONDS = 2 * 60 * 60

_LOCAL_CANCEL_REQUESTS: set[str] = set()

def _log_redis_failure(operation: str, exc: RedisError) -> None:
    """Keep Redis an optional cross-process enhancement, never an API SPOF."""
    _logger.warning("Analysis task store %s skipped because Redis is unavailable: %s", operation, exc)

def _owner_key(task_id: str) -> str:
    return f"analysis:owner:{task_id}"

def _meta_key(task_id: str) -> str:
    return f"analysis:meta:{task_id}"

def _user_tasks_key(user_id: int) -> str:
    return f"analysis:user_tasks:{user_id}"

def _cancel_key(task_id: str) -> str:
    return f"analysis:cancel:{task_id}"

async def set_owner(task_id: str, user_id: int | None) -> None:
    if not redis_enabled():
        return
    try:
        await get_redis().set(_owner_key(task_id), "" if user_id is None else str(user_id), ex=_TTL_SECONDS)
    except RedisError as exc:
        _log_redis_failure("set_owner", exc)

async def get_owner(task_id: str) -> int | None:
    """Owner user id, or ``None`` when unknown or system-owned."""
    if not redis_enabled():
        return None
    try:
        raw = await get_redis().get(_owner_key(task_id))
    except RedisError as exc:
        _log_redis_failure("get_owner", exc)
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        _logger.warning("Invalid owner value for task=%s: %r", task_id, raw)
        return None

async def clear_owner(task_id: str) -> None:
    if not redis_enabled():
        return
    try:
        await get_redis().delete(_owner_key(task_id))
    except RedisError as exc:
        _log_redis_failure("clear_owner", exc)

async def get_meta(task_id: str) -> dict | None:
    """Return task meta dict, or None when unknown."""
    if not redis_enabled():
        return None
    try:
        raw = await get_redis().get(_meta_key(task_id))
    except RedisError as exc:
        _log_redis_failure("get_meta", exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None

async def set_meta(task_id: str, meta: dict) -> None:
    if not redis_enabled():
        return
    try:
        redis = get_redis()
        await redis.set(_meta_key(task_id), json.dumps(meta), ex=_TTL_SECONDS)
        user_id = meta.get("user_id")
        if user_id is not None:
            key = _user_tasks_key(user_id)
            await redis.sadd(key, task_id)
            await redis.expire(key, _TTL_SECONDS)
    except RedisError as exc:
        _log_redis_failure("set_meta", exc)

async def clear_meta(task_id: str, user_id: int | None = None) -> None:
    if not redis_enabled():
        return
    try:
        redis = get_redis()
        await redis.delete(_meta_key(task_id))
        if user_id is not None:
            await redis.srem(_user_tasks_key(user_id), task_id)
    except RedisError as exc:
        _log_redis_failure("clear_meta", exc)

async def request_cancel(task_id: str) -> None:
    """Persist a cancellation request before publishing the transient signal.

    Redis pub/sub messages are intentionally ephemeral: a worker can receive
    no message when the job has not started yet.  This small TTL-bound marker
    lets the runner observe that intent when it eventually starts.  Without
    Redis, the same invariant is preserved by the local set above.
    """
    if not redis_enabled():
        _LOCAL_CANCEL_REQUESTS.add(task_id)
        return
    try:
        await get_redis().set(_cancel_key(task_id), "1", ex=_TTL_SECONDS)
    except RedisError as exc:
        _LOCAL_CANCEL_REQUESTS.add(task_id)
        _log_redis_failure("request_cancel", exc)

async def is_cancel_requested(task_id: str) -> bool:
    """Return whether a runner must terminate before doing more work."""
    if task_id in _LOCAL_CANCEL_REQUESTS:
        return True
    if not redis_enabled():
        return False
    try:
        return bool(await get_redis().get(_cancel_key(task_id)))
    except RedisError as exc:
        _log_redis_failure("is_cancel_requested", exc)
        return False

async def clear_cancel_request(task_id: str) -> None:
    """Acknowledge terminal handling of a cancellation request."""
    _LOCAL_CANCEL_REQUESTS.discard(task_id)
    if not redis_enabled():
        return
    try:
        await get_redis().delete(_cancel_key(task_id))
    except RedisError as exc:
        _log_redis_failure("clear_cancel_request", exc)

async def list_tasks_for_user(user_id: int) -> list[dict]:
    """Active tasks for ``user_id`` as ``{"task_id": ..., **meta}`` dicts."""
    if not redis_enabled():
        return []
    try:
        redis = get_redis()
        task_ids = await redis.smembers(_user_tasks_key(user_id))
    except RedisError as exc:
        _log_redis_failure("list_tasks_for_user", exc)
        return []
    tasks: list[dict] = []
    for task_id in task_ids:
        try:
            raw = await redis.get(_meta_key(task_id))
        except RedisError as exc:
            _log_redis_failure("list_tasks_for_user", exc)
            return tasks
        if raw is None:
            try:
                await redis.srem(_user_tasks_key(user_id), task_id)
            except RedisError as exc:
                _log_redis_failure("list_tasks_for_user", exc)
                return tasks
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
    try:
        await get_redis().publish(CONTROL_CHANNEL, json.dumps({"action": "cancel", "task_id": task_id}))
    except RedisError as exc:
        _log_redis_failure("publish_cancel", exc)

async def control_listener(cancel_local) -> None:
    """Listen for control messages and apply them to this process.

    ``cancel_local`` is an async callable ``(task_id) -> bool`` that cancels a
    task if it runs in the current process. Runs in web and worker processes.
    """

    async def handle(payload: dict) -> None:
        if payload.get("action") == "cancel" and payload.get("task_id"):
            await cancel_local(payload["task_id"])

    await subscribe_loop(CONTROL_CHANNEL, handle, name="Control listener")
