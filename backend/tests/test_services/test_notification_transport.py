import socket

import pytest

@pytest.mark.asyncio
async def test_webhook_resolution_returns_only_vetted_public_addresses(monkeypatch):
    from backend.services.notification_service import resolve_webhook_target

    def fake_getaddrinfo(host, port, proto):
        assert host == "hooks.example"
        assert port == 443
        assert proto == socket.IPPROTO_TCP
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", port)),
            (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("2606:4700:4700::1111", port, 0, 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    target = await resolve_webhook_target("https://hooks.example/path?secret=value")

    assert target.host == "hooks.example"
    assert target.port == 443
    assert target.addresses == ("1.1.1.1", "2606:4700:4700::1111")

@pytest.mark.asyncio
async def test_webhook_resolution_rejects_a_mixed_public_and_private_dns_answer(monkeypatch):
    from backend.services.notification_service import resolve_webhook_target

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, proto: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.1.1.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port)),
        ],
    )

    with pytest.raises(ValueError, match="disallowed internal address"):
        await resolve_webhook_target("https://hooks.example/path")

@pytest.mark.asyncio
async def test_pinned_webhook_backend_dials_vetted_ip_not_hostname():
    import httpcore

    from backend.services.notification_service import WebhookTarget, _PinnedWebhookNetworkBackend

    target = WebhookTarget(
        url="https://hooks.example/path",
        host="hooks.example",
        port=443,
        addresses=("1.1.1.1", "2606:4700:4700::1111"),
    )
    backend = _PinnedWebhookNetworkBackend(target)
    calls: list[tuple[str, int]] = []

    class Delegate:
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return object()

        async def sleep(self, seconds):
            return None

    backend._backend = Delegate()

    await backend.connect_tcp("hooks.example", 443)
    await backend.connect_tcp("hooks.example", 443)

    assert calls == [("1.1.1.1", 443), ("2606:4700:4700::1111", 443)]
    with pytest.raises(httpcore.ConnectError, match="unexpected destination"):
        await backend.connect_tcp("localhost", 443)

@pytest.mark.asyncio
async def test_pinned_transport_uses_vetted_ip_but_preserves_original_host_header():
    """Exercise httpx/httpcore's real connection-pool path without a socket.

    The sandbox intentionally disallows binding a local listener. A tiny
    httpcore stream double lets the actual AsyncHTTPTransport parse/write a
    request while proving the injected backend receives the vetted numeric IP
    and the HTTP layer keeps the original hostname.
    """
    import httpx

    from backend.services.notification_service import WebhookTarget, _pinned_webhook_transport

    port = 8080
    target = WebhookTarget(
        url=f"http://hooks.example:{port}/deliver",
        host="hooks.example",
        port=port,
        addresses=("1.1.1.1",),
    )
    transport = _pinned_webhook_transport(target)
    backend = transport._pool._network_backend
    captured: dict[str, object] = {"calls": [], "writes": []}

    class Stream:
        sent_response = False

        async def read(self, max_bytes, timeout=None):
            if self.sent_response:
                return b""
            self.sent_response = True
            return b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"

        async def write(self, buffer, timeout=None):
            captured["writes"].append(buffer)

        async def aclose(self):
            return None

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            return self

        def get_extra_info(self, info):
            return None

    class Delegate:
        async def connect_tcp(self, host, port, **kwargs):
            captured["calls"].append((host, port))
            return Stream()

        async def sleep(self, seconds):
            return None

    backend._backend = Delegate()
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
        response = await client.post(target.url, json={"ok": True})

    assert response.status_code == 204
    assert captured["calls"] == [("1.1.1.1", port)]
    assert f"Host: hooks.example:{port}".encode() in b"".join(captured["writes"])
