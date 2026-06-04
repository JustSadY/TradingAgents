import asyncio
import json
import logging
from collections import deque
from typing import Any
from fastapi import WebSocket
_logger = logging.getLogger(__name__)
_BUFFER_SIZE = 64
_BUFFER_TTL = 30
class WebSocketManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._buffers: dict[str, deque] = {}
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}
    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)
        _logger.debug("WS connected: task=%s", task_id)
        buffered = list(self._buffers.get(task_id, []))
        if buffered:
            _logger.debug("Replaying %d buffered events for task=%s", len(buffered), task_id)
            for event in buffered:
                try:
                    await ws.send_text(json.dumps(event, ensure_ascii=False))
                except Exception:
                    break
    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(task_id, None)
    async def send(self, task_id: str, event: dict[str, Any]):
        buf = self._buffers.setdefault(task_id, deque(maxlen=_BUFFER_SIZE))
        buf.append(event)
        text = json.dumps(event, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)
    async def close_task(self, task_id: str):
        for ws in list(self._connections.get(task_id, [])):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.pop(task_id, None)
        self._schedule_buffer_cleanup(task_id)
    def active_tasks(self) -> list[str]:
        return list(self._connections.keys())
    def _schedule_buffer_cleanup(self, task_id: str):
        existing = self._cleanup_handles.pop(task_id, None)
        if existing:
            try:
                existing.cancel()
            except Exception:
                pass
        loop = asyncio.get_event_loop()
        handle = loop.call_later(_BUFFER_TTL, self._cleanup_buffer, task_id)
        self._cleanup_handles[task_id] = handle
    def _cleanup_buffer(self, task_id: str):
        self._buffers.pop(task_id, None)
        self._cleanup_handles.pop(task_id, None)
        _logger.debug("Buffer cleaned up for task=%s", task_id)
ws_manager = WebSocketManager()
