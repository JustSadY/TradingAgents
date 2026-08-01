import asyncio
import json
import logging
from collections import deque
from typing import Any

from fastapi import WebSocket

from backend.core.metrics import WS_CONNECTIONS

_logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task] = set()
_BUFFER_SIZE = 10000
_BUFFER_TTL = 30

class _TaskLock:
    """An asyncio.Lock plus a count of coroutines currently holding a
    reference to it, so it's only safe to drop from the registry once no one
    is using it anymore (see WebSocketManager._acquire/_release)."""

    __slots__ = ("lock", "waiters")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.waiters = 0

class WebSocketManager:
    """Manages WebSocket connections with per-task locking for race safety.

    Thread-/task-safe guards
    ---------------------------
    - ``_task_locks``: each task_id has a ``_TaskLock`` (an ``asyncio.Lock``
      plus a reference count) so concurrent ``connect``/``disconnect``/
      ``send``/``close_task`` calls for the same task_id are serialised.
    - Buffer, connection-list, and cleanup-handle mutations always happen
      under the per-task lock.
    - The registry entry is only dropped once its reference count reaches
      zero (via ``_acquire``/``_release``), so a coroutine already waiting on
      or holding the lock can never have it swapped out from under it by a
      concurrent caller creating a *different* lock for the same task_id.
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._buffers: dict[str, deque] = {}
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}
        self._task_locks: dict[str, _TaskLock] = {}

    def _acquire(self, task_id: str) -> _TaskLock:
        """Get (creating if needed) the lock entry for *task_id* and mark it
        in-use. Must be paired with a later ``_release`` call. Synchronous —
        no ``await`` here, so this can't race with a concurrent caller."""
        entry = self._task_locks.get(task_id)
        if entry is None:
            entry = _TaskLock()
            self._task_locks[task_id] = entry
        entry.waiters += 1
        return entry

    def _release(self, task_id: str, entry: _TaskLock) -> None:
        """Mark *entry* no longer in-use; drop it from the registry once
        nothing else references it. Synchronous for the same reason as
        ``_acquire``."""
        entry.waiters -= 1
        if entry.waiters <= 0 and self._task_locks.get(task_id) is entry:
            del self._task_locks[task_id]

    def _refresh_connection_gauge(self):
        WS_CONNECTIONS.set(sum(len(conns) for conns in self._connections.values()))

    async def connect(self, task_id: str, ws: WebSocket, *, subprotocol: str | None = None):
        """Accept and register a task stream, optionally negotiating a safe protocol."""
        await ws.accept(subprotocol=subprotocol)
        entry = self._acquire(task_id)
        try:
            async with entry.lock:
                self._connections.setdefault(task_id, []).append(ws)
                self._refresh_connection_gauge()
                buffered = list(self._buffers.get(task_id, []))
                _logger.debug("WS connected: task=%s", task_id)
                if buffered:
                    _logger.debug("Replaying %d buffered events for task=%s", len(buffered), task_id)
                    for event in buffered:
                        try:
                            await ws.send_text(json.dumps(event, ensure_ascii=False))
                        except Exception:
                            break
        finally:
            self._release(task_id, entry)

    async def disconnect(self, task_id: str, ws: WebSocket):
        entry = self._acquire(task_id)
        try:
            async with entry.lock:
                conns = self._connections.get(task_id, [])
                if ws in conns:
                    conns.remove(ws)
                if not conns:
                    self._connections.pop(task_id, None)
                self._refresh_connection_gauge()
        finally:
            self._release(task_id, entry)

    async def send(self, task_id: str, event: dict[str, Any]):
        entry = self._acquire(task_id)
        try:
            async with entry.lock:
                buf = self._buffers.setdefault(task_id, deque(maxlen=_BUFFER_SIZE))
                buf.append(event)
                self._schedule_buffer_cleanup(task_id, ttl=600)
                text = json.dumps(event, ensure_ascii=False)
                active_conns = list(self._connections.get(task_id, []))
                if not active_conns:
                    return
                dead: list[WebSocket] = []
                results = await asyncio.gather(*[ws.send_text(text) for ws in active_conns], return_exceptions=True)
                for i, res in enumerate(results):
                    if isinstance(res, Exception):
                        dead.append(active_conns[i])
                        _logger.debug("WS send failed for task=%s, marking as dead: %s", task_id, res)
                for ws in dead:
                    conns = self._connections.get(task_id, [])
                    if ws in conns:
                        conns.remove(ws)
                if not self._connections.get(task_id):
                    self._connections.pop(task_id, None)
                self._refresh_connection_gauge()
        finally:
            self._release(task_id, entry)

    async def close_task(self, task_id: str):
        entry = self._acquire(task_id)
        try:
            async with entry.lock:
                for ws in list(self._connections.get(task_id, [])):
                    try:
                        await ws.close()
                    except Exception:
                        _logger.debug("WS close failed for task=%s (cleanup)", task_id)
                self._connections.pop(task_id, None)
                self._refresh_connection_gauge()
                self._schedule_buffer_cleanup(task_id, ttl=_BUFFER_TTL)
        finally:
            self._release(task_id, entry)

    def _schedule_buffer_cleanup(self, task_id: str, ttl: int = _BUFFER_TTL):
        existing = self._cleanup_handles.pop(task_id, None)
        if existing:
            try:
                existing.cancel()
            except Exception:
                _logger.debug("Cleanup handle cancel failed for task=%s", task_id)
        loop = asyncio.get_running_loop()
        handle = loop.call_later(ttl, self._cleanup_buffer, task_id)
        self._cleanup_handles[task_id] = handle

    def _cleanup_buffer(self, task_id: str):
        if task_id in self._task_locks:
            _logger.debug("Skipping buffer cleanup for task=%s — lock in use, will retry", task_id)
            handle = asyncio.get_running_loop().call_later(1.0, self._cleanup_buffer, task_id)
            self._cleanup_handles[task_id] = handle
            return
        self._buffers.pop(task_id, None)
        self._cleanup_handles.pop(task_id, None)
        conns = self._connections.pop(task_id, None)
        self._refresh_connection_gauge()
        if conns:
            _logger.debug("Closing %d lingering WS connections for task=%s during buffer cleanup", len(conns), task_id)
            for ws in conns:
                try:
                    task = asyncio.create_task(ws.close())
                    _BACKGROUND_TASKS.add(task)
                    task.add_done_callback(_BACKGROUND_TASKS.discard)
                except Exception:
                    _logger.debug("Lingering WS close task creation failed for task=%s", task_id)
        _logger.debug("Buffer cleaned up for task=%s", task_id)

ws_manager = WebSocketManager()
