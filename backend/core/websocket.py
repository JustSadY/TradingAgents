import asyncio
import json
import logging
import threading
from collections import deque
from typing import Any, Callable, Coroutine

from fastapi import WebSocket

from backend.core.metrics import WS_CONNECTIONS

_logger = logging.getLogger(__name__)

_BUFFER_SIZE = 10000
_BUFFER_TTL = 30
_ACTIVE_BUFFER_TTL = 600
_REPLAYABLE_EVENT_TYPES = {
    "report",
    "debate_bubble",
    "risk_metrics",
    "decision",
    "order_result",
    "complete",
    "error",
    "stats",
}


class _SocketBinding:
    """A WebSocket plus the event loop that owns its ASGI send channel.

    Cross-loop callers never await this binding's ``send_lock`` directly.
    They marshal the whole send/close coroutine onto ``loop`` first, so the
    asyncio primitive and the WebSocket transport are always touched from the
    loop that accepted the socket.
    """

    __slots__ = ("ws", "loop", "send_lock")

    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop) -> None:
        self.ws = ws
        self.loop = loop
        self.send_lock = asyncio.Lock()


class WebSocketManager:
    """Manage analysis WebSockets safely across multiple asyncio event loops.

    The manager is process-global, while WebSocket requests, background
    analysis work, test clients, and Redis forwarders may execute on different
    event loops. A process-global ``asyncio.Lock`` therefore cannot guard task
    state: once awaited by one loop it raises ``bound to a different event
    loop`` from another.

    Shared Python containers are protected only by a short-lived
    ``threading.RLock`` (never held across ``await``). Each actual socket send
    or close is marshalled back to the loop that accepted that socket.
    """

    def __init__(self):
        self._connections: dict[str, list[_SocketBinding]] = {}
        self._buffers: dict[str, deque] = {}
        self._cleanup_handles: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.TimerHandle, int]] = {}
        self._cleanup_generation: dict[str, int] = {}
        self._guard = threading.RLock()

    def _refresh_connection_gauge_locked(self) -> None:
        WS_CONNECTIONS.set(sum(len(conns) for conns in self._connections.values()))

    @staticmethod
    async def _run_on_loop(
        loop: asyncio.AbstractEventLoop,
        factory: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        current = asyncio.get_running_loop()
        if current is loop:
            return await factory()
        if loop.is_closed() or not loop.is_running():
            raise RuntimeError("WebSocket owner event loop is no longer running")
        future = asyncio.run_coroutine_threadsafe(factory(), loop)
        return await asyncio.wrap_future(future)

    async def _send_binding(self, binding: _SocketBinding, text: str) -> None:
        async def _send() -> None:
            async with binding.send_lock:
                await binding.ws.send_text(text)

        await self._run_on_loop(binding.loop, _send)

    async def _close_binding(self, binding: _SocketBinding) -> None:
        async def _close() -> None:
            async with binding.send_lock:
                try:
                    await binding.ws.close()
                except Exception:
                    _logger.debug("WS close failed during cleanup", exc_info=True)

        await self._run_on_loop(binding.loop, _close)

    def _remove_binding(self, task_id: str, binding: _SocketBinding) -> None:
        with self._guard:
            conns = self._connections.get(task_id, [])
            if binding in conns:
                conns.remove(binding)
            if not conns:
                self._connections.pop(task_id, None)
            self._refresh_connection_gauge_locked()

    def _cancel_cleanup_locked(self, task_id: str) -> None:
        record = self._cleanup_handles.pop(task_id, None)
        if not record:
            return
        loop, handle, _generation = record
        if loop.is_closed():
            return
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            handle.cancel()
        elif loop.is_running():
            try:
                loop.call_soon_threadsafe(handle.cancel)
            except RuntimeError:
                pass

    def _schedule_buffer_cleanup(self, task_id: str, ttl: int = _BUFFER_TTL) -> None:
        loop = asyncio.get_running_loop()
        with self._guard:
            self._cancel_cleanup_locked(task_id)
            generation = self._cleanup_generation.get(task_id, 0) + 1
            self._cleanup_generation[task_id] = generation
            handle = loop.call_later(ttl, self._cleanup_buffer, task_id, generation)
            self._cleanup_handles[task_id] = (loop, handle, generation)

    def _cleanup_buffer(self, task_id: str, generation: int) -> None:
        """Drop only detached buffers; never close a live socket from a timer."""
        with self._guard:
            record = self._cleanup_handles.get(task_id)
            if not record or record[2] != generation:
                return
            if self._connections.get(task_id):
                # A connected client still owns the stream. Heartbeat/live
                # events normally refresh the timer, but fail safe and retry
                # instead of deleting state underneath an active socket.
                loop = asyncio.get_running_loop()
                next_generation = generation + 1
                self._cleanup_generation[task_id] = next_generation
                handle = loop.call_later(_BUFFER_TTL, self._cleanup_buffer, task_id, next_generation)
                self._cleanup_handles[task_id] = (loop, handle, next_generation)
                return
            self._buffers.pop(task_id, None)
            self._cleanup_handles.pop(task_id, None)
            self._cleanup_generation.pop(task_id, None)
            _logger.debug("Buffer cleaned up for task=%s", task_id)

    async def connect(self, task_id: str, ws: WebSocket, *, subprotocol: str | None = None):
        """Accept/register a task stream and restore durable UI state only."""
        await ws.accept(subprotocol=subprotocol)
        loop = asyncio.get_running_loop()
        binding = _SocketBinding(ws, loop)
        with self._guard:
            self._connections.setdefault(task_id, []).append(binding)
            self._refresh_connection_gauge_locked()
            buffered = [dict(event) for event in self._buffers.get(task_id, []) if event.get("type") in _REPLAYABLE_EVENT_TYPES]
        _logger.debug("WS connected: task=%s", task_id)

        # Reconnect is state restoration, not a replay of the analysis UI.
        # Transient status/progress/token/mental-model events are deliberately
        # omitted so a page refresh does not look like the scan started again.
        if buffered:
            _logger.debug("Restoring %d buffered state events for task=%s", len(buffered), task_id)
        try:
            for event in buffered:
                replay_event = {**event, "replay": True}
                await self._send_binding(binding, json.dumps(replay_event, ensure_ascii=False))
        except Exception:
            self._remove_binding(task_id, binding)
            raise

    async def disconnect(self, task_id: str, ws: WebSocket):
        """Remove a socket without touching any loop-bound asyncio primitive."""
        with self._guard:
            conns = self._connections.get(task_id, [])
            conns[:] = [binding for binding in conns if binding.ws is not ws]
            if not conns:
                self._connections.pop(task_id, None)
            self._refresh_connection_gauge_locked()

    async def send(self, task_id: str, event: dict[str, Any]):
        stored_event = dict(event)
        with self._guard:
            buf = self._buffers.setdefault(task_id, deque(maxlen=_BUFFER_SIZE))
            buf.append(stored_event)
            active_conns = list(self._connections.get(task_id, []))
        self._schedule_buffer_cleanup(task_id, ttl=_ACTIVE_BUFFER_TTL)

        if not active_conns:
            return

        text = json.dumps(event, ensure_ascii=False)
        results = await asyncio.gather(
            *[self._send_binding(binding, text) for binding in active_conns],
            return_exceptions=True,
        )
        dead: list[_SocketBinding] = []
        for binding, result in zip(active_conns, results, strict=False):
            if isinstance(result, Exception):
                dead.append(binding)
                _logger.debug("WS send failed for task=%s, marking as dead: %s", task_id, result)

        if dead:
            with self._guard:
                conns = self._connections.get(task_id, [])
                conns[:] = [binding for binding in conns if binding not in dead]
                if not conns:
                    self._connections.pop(task_id, None)
                self._refresh_connection_gauge_locked()

    async def close_task(self, task_id: str):
        with self._guard:
            bindings = list(self._connections.pop(task_id, []))
            self._refresh_connection_gauge_locked()

        if bindings:
            await asyncio.gather(*[self._close_binding(binding) for binding in bindings], return_exceptions=True)
        self._schedule_buffer_cleanup(task_id, ttl=_BUFFER_TTL)


ws_manager = WebSocketManager()
