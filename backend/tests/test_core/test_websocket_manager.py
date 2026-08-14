from __future__ import annotations

import asyncio
import json
import threading

import pytest

from backend.core.websocket import WebSocketManager


class _Socket:
    def __init__(self) -> None:
        self.owner_loop: asyncio.AbstractEventLoop | None = None
        self.accepted = False
        self.sent: list[dict] = []
        self.closed = False

    async def accept(self, *, subprotocol: str | None = None) -> None:
        self.owner_loop = asyncio.get_running_loop()
        self.accepted = True

    async def send_text(self, text: str) -> None:
        assert asyncio.get_running_loop() is self.owner_loop
        self.sent.append(json.loads(text))

    async def close(self) -> None:
        assert asyncio.get_running_loop() is self.owner_loop
        self.closed = True


def test_disconnect_and_reconnect_do_not_reuse_a_lock_from_an_old_event_loop() -> None:
    manager = WebSocketManager()
    first = _Socket()
    second = _Socket()

    loop_one = asyncio.new_event_loop()
    loop_one.run_until_complete(manager.connect("task", first))
    loop_one.close()

    loop_two = asyncio.new_event_loop()
    try:
        # This sequence reproduces the production refresh path that previously
        # raised "asyncio.Lock ... is bound to a different event loop".
        loop_two.run_until_complete(manager.disconnect("task", first))
        loop_two.run_until_complete(manager.connect("task", second))
        loop_two.run_until_complete(manager.disconnect("task", second))
    finally:
        loop_two.close()

    assert first.accepted is True
    assert second.accepted is True


@pytest.mark.asyncio
async def test_cross_loop_send_and_close_are_marshaled_to_the_socket_owner_loop() -> None:
    manager = WebSocketManager()
    socket = _Socket()
    owner_loop = asyncio.new_event_loop()
    started = threading.Event()

    def run_owner_loop() -> None:
        asyncio.set_event_loop(owner_loop)
        started.set()
        owner_loop.run_forever()

    thread = threading.Thread(target=run_owner_loop, daemon=True)
    thread.start()
    assert started.wait(timeout=2)

    try:
        connect = asyncio.run_coroutine_threadsafe(manager.connect("task", socket), owner_loop)
        connect.result(timeout=2)

        await manager.send("task", {"type": "report", "section": "market_report", "content": "ready"})
        assert socket.sent[-1]["content"] == "ready"

        await manager.close_task("task")
        assert socket.closed is True
    finally:
        owner_loop.call_soon_threadsafe(owner_loop.stop)
        thread.join(timeout=2)
        owner_loop.close()


@pytest.mark.asyncio
async def test_reconnect_replays_state_without_replaying_scan_progress() -> None:
    manager = WebSocketManager()

    await manager.send("task", {"type": "status", "status": "running", "message": "Starting Market Analyst"})
    await manager.send("task", {"type": "progress", "label": "Market Analyst", "stage": "running"})
    await manager.send("task", {"type": "token", "agent": "market", "token": "partial"})
    await manager.send("task", {"type": "report", "section": "market_report", "content": "final market report"})
    await manager.send(
        "task",
        {
            "type": "debate_bubble",
            "debate_type": "investment",
            "message": "Bull Analyst: evidence",
            "sender": "Bull Analyst",
            "content": "evidence",
        },
    )

    socket = _Socket()
    await manager.connect("task", socket)

    assert [event["type"] for event in socket.sent] == ["report", "debate_bubble"]
    assert all(event["replay"] is True for event in socket.sent)

    await manager.disconnect("task", socket)
    await manager.close_task("task")
