from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from backend.services import notification_service


class _Client:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, _url: str, *, json: dict):
        self.calls += 1
        assert isinstance(json, dict)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _response(status_code: int, headers: dict[str, str] | None = None):
    return SimpleNamespace(status_code=status_code, headers=headers or {})


def _target(url: str = "https://hooks.example/deliver") -> notification_service.WebhookTarget:
    return notification_service.WebhookTarget(
        url=url,
        host="hooks.example",
        port=443,
        addresses=("1.1.1.1",),
    )


async def _install_delivery_doubles(monkeypatch, client: _Client) -> list[str]:
    resolutions: list[str] = []

    async def resolve(url: str):
        resolutions.append(url)
        return _target(url)

    monkeypatch.setattr(notification_service, "resolve_webhook_target", resolve)
    monkeypatch.setattr(notification_service, "_webhook_client", lambda target: client)
    monkeypatch.setattr(notification_service, "_webhook_retry_wait", lambda _state: 0.0)
    return resolutions


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
async def test_retryable_http_status_retries_then_succeeds(monkeypatch, status_code: int):
    client = _Client([_response(status_code), _response(204)])
    resolutions = await _install_delivery_doubles(monkeypatch, client)
    url = "https://hooks.example/deliver"

    assert await notification_service.send_webhook(url, "analysis_complete", {}, retries=2) is True

    assert client.calls == 2
    assert resolutions == [url]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [301, 400, 401, 403, 404, 501])
async def test_permanent_http_status_is_not_retried(monkeypatch, status_code: int):
    client = _Client([_response(status_code)])
    resolutions = await _install_delivery_doubles(monkeypatch, client)
    url = "https://hooks.example/deliver"

    assert await notification_service.send_webhook(url, "analysis_complete", {}, retries=3) is False

    assert client.calls == 1
    assert resolutions == [url]


@pytest.mark.asyncio
async def test_request_error_retries_without_resolving_dns_again(monkeypatch):
    request = httpx.Request("POST", "https://hooks.example/deliver")
    client = _Client([httpx.ConnectError("temporary network failure", request=request), _response(204)])
    resolutions = await _install_delivery_doubles(monkeypatch, client)
    url = "https://hooks.example/deliver"

    assert await notification_service.send_webhook(url, "trade_executed", {}, retries=2) is True

    assert client.calls == 2
    assert resolutions == [url]


@pytest.mark.asyncio
async def test_zero_retries_still_performs_exactly_one_attempt(monkeypatch):
    client = _Client([_response(503)])
    resolutions = await _install_delivery_doubles(monkeypatch, client)
    url = "https://hooks.example/deliver"

    assert await notification_service.send_webhook(url, "alert_triggered", {}, retries=0) is False

    assert client.calls == 1
    assert resolutions == [url]


def test_retry_after_seconds_accepts_seconds_and_caps_untrusted_delay():
    assert notification_service._retry_after_seconds(_response(429, {"Retry-After": "7"})) == 7.0
    assert (
        notification_service._retry_after_seconds(_response(429, {"Retry-After": "600"}))
        == notification_service._MAX_RETRY_AFTER_SECONDS
    )
    assert notification_service._retry_after_seconds(_response(429, {"Retry-After": "not-a-date"})) is None


def test_retry_after_overrides_jitter_wait():
    retry_state = SimpleNamespace(
        attempt_number=1,
        outcome=SimpleNamespace(
            exception=lambda: notification_service._RetryableWebhookResponse(429, retry_after=7.0)
        ),
    )

    assert notification_service._webhook_retry_wait(retry_state) == 7.0
