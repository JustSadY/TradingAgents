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
    assert get_websocket_application_subprotocol(f"{WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token") is None

@pytest.mark.asyncio
async def test_websocket_rejects_a_handshake_without_the_application_protocol():
    """The authenticated socket contract always includes the application protocol."""
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

@pytest.mark.asyncio
async def test_connected_websocket_revalidation_checks_current_token_and_page_access(monkeypatch):
    from types import SimpleNamespace

    import backend.api.deps as deps
    import backend.core.database as database
    from backend.main import _analysis_websocket_access_is_current

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    async def current_user(token, db):
        assert token == "header-token"
        return SimpleNamespace(id=7)

    async def page_access(db, user, page):
        assert page == "analysis"
        return True

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(deps, "get_user_from_access_token", current_user)
    monkeypatch.setattr(deps, "has_page_access", page_access)

    assert await _analysis_websocket_access_is_current("header-token", 7) is True
    assert await _analysis_websocket_access_is_current("header-token", 8) is False

@pytest.mark.asyncio
async def test_connected_websocket_closes_when_periodic_revalidation_is_revoked(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import backend.api.deps as deps
    import backend.core.database as database
    import backend.main as main
    import backend.services.analysis_service as analysis_service

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class Socket:
        headers = {
            "sec-websocket-protocol": (
                f"{WEBSOCKET_APPLICATION_SUBPROTOCOL}, {WEBSOCKET_TOKEN_SUBPROTOCOL_PREFIX}header-token"
            )
        }

        def __init__(self):
            self.calls: list[tuple] = []

        async def accept(self, *, subprotocol=None):
            self.calls.append(("accept", subprotocol))

        async def close(self, *, code, reason):
            self.calls.append(("close", code, reason))

        async def receive_text(self):
            await asyncio.sleep(10)
            return "never"

    user_calls = 0

    async def get_user(token, db):
        nonlocal user_calls
        user_calls += 1
        if user_calls == 1:
            return SimpleNamespace(id=7, is_admin=False)
        raise main.HTTPException(status_code=401)

    async def page_access(db, user, page):
        return True

    async def owns_task(task_id, user_id, is_admin):
        return True

    async def connect(task_id, socket, *, subprotocol=None):
        await socket.accept(subprotocol=subprotocol)

    async def disconnect(task_id, socket):
        return None

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr(deps, "get_user_from_access_token", get_user)
    monkeypatch.setattr(deps, "has_page_access", page_access)
    monkeypatch.setattr(analysis_service, "is_task_owner", owns_task)
    monkeypatch.setattr(main.ws_manager, "connect", connect)
    monkeypatch.setattr(main.ws_manager, "disconnect", disconnect)
    monkeypatch.setattr(main, "_WS_AUTH_REVALIDATION_SECONDS", 0.001)

    socket = Socket()
    await main.websocket_analysis(socket, "task-id")

    assert socket.calls == [
        ("accept", WEBSOCKET_APPLICATION_SUBPROTOCOL),
        ("close", 4001, "Unauthorized"),
    ]
