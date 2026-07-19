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


class WebSocketManager:
    """Manages WebSocket connections with per-task locking for race safety.

    Thread-/task-safe guards
    ---------------------------
    - ``_task_locks``: each task_id has an ``asyncio.Lock`` so concurrent
      ``connect``/``disconnect``/``send``/``close_task`` calls for the same
      task_id are serialised.
    - Buffer, connection-list, and cleanup-handle mutations always happen
      under the per-task lock.
    - The lock is lazily created and pruned from the dict when the task
      no longer has connections.
    """

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._buffers: dict[str, deque] = {}
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}
        self._task_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, task_id: str) -> asyncio.Lock:
        if task_id not in self._task_locks:
            self._task_locks[task_id] = asyncio.Lock()
        return self._task_locks[task_id]

    def _prune_lock(self, task_id: str) -> None:
        self._task_locks.pop(task_id, None)

    def _refresh_connection_gauge(self):
        WS_CONNECTIONS.set(sum(len(conns) for conns in self._connections.values()))

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        buffered: list = []
        async with self._get_lock(task_id):
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

    async def disconnect(self, task_id: str, ws: WebSocket):
        async with self._get_lock(task_id):
            conns = self._connections.get(task_id, [])
            if ws in conns:
                conns.remove(ws)
            if not conns:
                self._connections.pop(task_id, None)
                self._prune_lock(task_id)
            self._refresh_connection_gauge()

    async def send(self, task_id: str, event: dict[str, Any]):
        async with self._get_lock(task_id):
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
                self._prune_lock(task_id)
            self._refresh_connection_gauge()

    async def close_task(self, task_id: str):
        async with self._get_lock(task_id):
            for ws in list(self._connections.get(task_id, [])):
                try:
                    await ws.close()
                except Exception:
                    _logger.debug("WS close failed for task=%s (cleanup)", task_id)
            self._connections.pop(task_id, None)
            self._prune_lock(task_id)
            self._refresh_connection_gauge()
            self._schedule_buffer_cleanup(task_id, ttl=_BUFFER_TTL)

    def _schedule_buffer_cleanup(self, task_id: str, ttl: int = _BUFFER_TTL):
        existing = self._cleanup_handles.pop(task_id, None)
        if existing:
            try:
                existing.cancel()
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        handle = loop.call_later(ttl, self._cleanup_buffer, task_id)
        self._cleanup_handles[task_id] = handle

    def _cleanup_buffer(self, task_id: str):
        lock = self._task_locks.get(task_id)
        if lock and lock.locked():
            _logger.debug("Skipping buffer cleanup for task=%s — lock in use, will retry", task_id)
            handle = asyncio.get_running_loop().call_later(1.0, self._cleanup_buffer, task_id)
            self._cleanup_handles[task_id] = handle
            return
        # Lock is free; proceed — caller is the event loop, not a concurrent coroutine.
        self._buffers.pop(task_id, None)
        self._cleanup_handles.pop(task_id, None)
        conns = self._connections.pop(task_id, None)
        self._prune_lock(task_id)
        self._refresh_connection_gauge()
        if conns:
            _logger.debug("Closing %d lingering WS connections for task=%s during buffer cleanup", len(conns), task_id)
            for ws in conns:
                try:
                    task = asyncio.create_task(ws.close())
                    _BACKGROUND_TASKS.add(task)
                    task.add_done_callback(_BACKGROUND_TASKS.discard)
                except Exception:
                    pass
        _logger.debug("Buffer cleaned up for task=%s", task_id)


ws_manager = WebSocketManager()
