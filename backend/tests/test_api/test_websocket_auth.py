import pytest

from backend.api.deps import WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX, get_websocket_access_token


def test_websocket_auth_prefers_private_subprotocol_over_legacy_query_token():
    token = get_websocket_access_token(
        f"chat.v1, {WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token",
        query_token="legacy-token",
    )

    assert token == "header-token"


def test_websocket_auth_uses_legacy_token_only_when_no_private_protocol_exists():
    assert get_websocket_access_token(None, query_token="legacy-token") == "legacy-token"
    assert get_websocket_access_token("chat.v1", query_token="legacy-token") == "legacy-token"


def test_websocket_auth_rejects_empty_private_protocol_token():
    assert get_websocket_access_token(WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX) is None


@pytest.mark.asyncio
async def test_websocket_rejection_sends_a_diagnostic_close_frame():
    """Clients need a WebSocket close code, not an opaque HTTP rejection."""
    from backend.main import _reject_websocket

    class Socket:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def accept(self) -> None:
            self.calls.append(("accept",))

        async def close(self, *, code: int, reason: str) -> None:
            self.calls.append(("close", code, reason))

    socket = Socket()
    await _reject_websocket(socket, code=4001, reason="Unauthorized")

    assert socket.calls == [("accept",), ("close", 4001, "Unauthorized")]
