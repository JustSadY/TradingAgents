"""Analysis event distribution: direct in-process or via Redis pub/sub.

``publish_event``/``publish_close`` are the single write path for analysis
WebSocket events. Without Redis they call the local ``ws_manager`` directly
(original behaviour). With Redis they PUBLISH to ``analysis:events``; every
web process runs ``event_forwarder`` which delivers received events to its
local ``ws_manager`` so clients connected to any process see the stream —
including runs executed in a separate arq worker process.

Deduplication
-------------
Each event carries an ``_eid`` (content hash + task_id + a per-task
monotonic sequence number assigned once per ``publish_event``/
``publish_close`` call). The forwarder keeps a bounded LRU of recently-seen
eids and skips delivery when the same *eid* arrives twice within a sliding
window (default 30s). This prevents duplicate delivery when:
- Two forwarder tasks are accidentally started in the same process.
- The same event is published to Redis twice (e.g. retry logic).
- A local process sends directly AND via Redis simultaneously.

The sequence number matters because dedup is content-hash based: without it,
two *legitimately* identical events for the same task (e.g. the same
"heartbeat" progress message re-emitted after a retry) would hash to the same
id and the second one would be silently dropped as a false-positive
duplicate. Folding in the sequence number makes every real ``publish_event``
call's id unique, while a redelivery of that *same* call (same seq, embedded
in the Redis payload) still shares its id and is correctly deduped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from backend.core.redis_bus import EVENTS_CHANNEL, get_redis, redis_enabled, subscribe_loop
from backend.core.websocket import ws_manager

_logger = logging.getLogger(__name__)

_CLOSE_TYPE = "__task_close__"
_DEDUP_WINDOW = 30
_DEDUP_MAX = 50000


def _event_id(task_id: str, event: dict[str, Any], seq: int) -> str:
    """Deterministic event identity for deduplication.

    Includes *seq* (see module docstring) so two content-identical events for
    the same task get distinct ids — only true redeliveries of the same
    publish call, which carry the same seq, are deduped.
    """
    raw = json.dumps({"task_id": task_id, "event": event, "_seq": seq}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


# Per-task monotonic counters backing the sequence numbers above. Small
# (one int per active task_id); cleared on publish_close so it doesn't grow
# unbounded over the server's lifetime.
_seq_counters: dict[str, int] = {}


def _next_seq(task_id: str) -> int:
    seq = _seq_counters.get(task_id, 0) + 1
    _seq_counters[task_id] = seq
    return seq


class _DedupTracker:
    """Bounded, time-windowed deduplication set.

    Thread-safe for asyncio single-thread usage. Evicts entries older than
    ``window`` seconds when ``_seen`` exceeds ``maxlen``.
    """

    def __init__(self, window: int = _DEDUP_WINDOW, maxlen: int = _DEDUP_MAX):
        self._window = window
        self._maxlen = maxlen
        self._seen: OrderedDict[str, float] = OrderedDict()

    def seen(self, eid: str) -> bool:
        now = time.monotonic()
        self._evict(now)
        if eid in self._seen:
            return True
        if len(self._seen) >= self._maxlen:
            self._seen.popitem(last=False)
        self._seen[eid] = now
        return False

    def _evict(self, now: float) -> None:
        cutoff = now - self._window
        while self._seen and next(iter(self._seen.values())) < cutoff:
            self._seen.popitem(last=False)


_dedup = _DedupTracker()


async def publish_event(task_id: str, event: dict[str, Any]) -> None:
    eid = _event_id(task_id, event, _next_seq(task_id))
    if redis_enabled():
        # Delivery happens through this process's pub/sub forwarder as well as
        # the other web processes.  Do not mark the id as seen here: doing so
        # makes the local forwarder discard every event that this process
        # published (the normal Redis + inline-queue configuration).
        redis = get_redis()
        await redis.publish(
            EVENTS_CHANNEL, json.dumps({"task_id": task_id, "event": event, "_eid": eid}, ensure_ascii=False)
        )
        return
    if _dedup.seen(eid):
        _logger.debug("Dedup: skipping duplicate send of event %s for task=%s", event.get("type"), task_id)
        return
    await ws_manager.send(task_id, event)


async def publish_close(task_id: str) -> None:
    eid = _event_id(task_id, {"type": _CLOSE_TYPE}, _next_seq(task_id))
    # No more events are expected for this task after close — drop its
    # sequence counter so _seq_counters doesn't grow for the server's entire
    # lifetime.
    _seq_counters.pop(task_id, None)
    if redis_enabled():
        redis = get_redis()
        await redis.publish(
            EVENTS_CHANNEL,
            json.dumps({"task_id": task_id, "event": {"type": _CLOSE_TYPE}, "_eid": eid}, ensure_ascii=False),
        )
        return
    if _dedup.seen(eid):
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
        eid = payload.get("_eid")
        if eid and _dedup.seen(eid):
            return
        await _deliver(payload["task_id"], payload["event"])

    await subscribe_loop(EVENTS_CHANNEL, deliver, name="Event forwarder")
