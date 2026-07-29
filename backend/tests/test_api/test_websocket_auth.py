import pytest

from backend.api.deps import (
    WEBSOCKET_APPLICATION_SUBPROTOCOL,
    WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX,
    get_websocket_access_token,
    get_websocket_application_subprotocol,
)


def test_websocket_auth_reads_private_subprotocol_token():
    token = get_websocket_access_token(f"chat.v1, {WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token")

    assert token == "header-token"


def test_websocket_auth_requires_a_private_subprotocol_token():
    assert get_websocket_access_token(None) is None
    assert get_websocket_access_token("chat.v1") is None


def test_websocket_auth_rejects_empty_private_protocol_token():
    assert get_websocket_access_token(WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX) is None


def test_websocket_selects_only_fixed_application_subprotocol():
    offered = f"{WEBSOCKET_APPLICATION_SUBPROTOCOL}, {WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token"

    assert get_websocket_application_subprotocol(offered) == WEBSOCKET_APPLICATION_SUBPROTOCOL
    # The JWT-bearing offer is request-only and must never appear in the 101
    # response header where a proxy/browser could retain it.
    assert get_websocket_application_subprotocol(f"{WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token") is None


@pytest.mark.asyncio
async def test_websocket_rejects_a_handshake_without_the_application_protocol():
    """A JWT-only offer is the removed legacy protocol contract."""
    from backend.main import websocket_analysis

    class Socket:
        headers = {"sec-websocket-protocol": f"{WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token"}

        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def accept(self, *, subprotocol: str | None = None) -> None:
            self.calls.append(("accept", subprotocol))

        async def close(self, *, code: int, reason: str) -> None:
            self.calls.append(("close", code, reason))

    socket = Socket()
    await websocket_analysis(socket, "task-id")

    assert socket.calls == [
        ("accept", None),
        ("close", 1002, "Unsupported WebSocket protocol"),
    ]


@pytest.mark.asyncio
async def test_websocket_rejects_an_application_protocol_without_a_private_jwt():
    from backend.main import websocket_analysis

    class Socket:
        headers = {"sec-websocket-protocol": WEBSOCKET_APPLICATION_SUBPROTOCOL}

        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def accept(self, *, subprotocol: str | None = None) -> None:
            self.calls.append(("accept", subprotocol))

        async def close(self, *, code: int, reason: str) -> None:
            self.calls.append(("close", code, reason))

    socket = Socket()
    await websocket_analysis(socket, "task-id")

    assert socket.calls == [
        ("accept", WEBSOCKET_APPLICATION_SUBPROTOCOL),
        ("close", 4001, "Unauthorized"),
    ]


@pytest.mark.asyncio
async def test_websocket_rejection_sends_a_diagnostic_close_frame():
    """Clients need a WebSocket close code, not an opaque HTTP rejection."""
    from backend.main import _reject_websocket

    class Socket:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def accept(self, *, subprotocol: str | None = None) -> None:
            self.calls.append(("accept", subprotocol))

        async def close(self, *, code: int, reason: str) -> None:
            self.calls.append(("close", code, reason))

    socket = Socket()
    await _reject_websocket(
        socket,
        code=4001,
        reason="Unauthorized",
        subprotocol=WEBSOCKET_APPLICATION_SUBPROTOCOL,
    )

    assert socket.calls == [
        ("accept", WEBSOCKET_APPLICATION_SUBPROTOCOL),
        ("close", 4001, "Unauthorized"),
    ]
