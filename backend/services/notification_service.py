import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from tenacity import AsyncRetrying, RetryCallState, retry_if_exception_type, stop_after_attempt

from backend.core.constants import WEBHOOK_EVENTS, signal_direction

_logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task] = set()
_RETRYABLE_WEBHOOK_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_SECONDS = 60.0


class _RetryableWebhookError(Exception):
    """Internal marker for delivery failures that may succeed on retry."""


class _RetryableWebhookResponse(_RetryableWebhookError):
    def __init__(self, status_code: int, *, retry_after: float | None = None) -> None:
        super().__init__(f"Webhook returned retryable HTTP {status_code}")
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class WebhookTarget:
    """A URL plus the public IPs vetted for this individual delivery.

    Resolving and then giving the original hostname back to a normal HTTP
    client leaves a DNS-rebinding window: the client performs a second lookup
    and can be sent to localhost after validation. A target instead carries
    the exact addresses that passed the public-address check, and the custom
    transport below dials only those addresses while retaining the original
    hostname for HTTP Host and HTTPS SNI/certificate validation.
    """

    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


async def _log_delivery(
    user_id: int,
    event: str,
    url: str,
    success: bool,
    status_code: int | None,
    error: str | None,
) -> None:
    """Write a delivery record. Opens its own session to avoid conflicts."""
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.models.webhook_delivery import WebhookDelivery

        async with AsyncSessionLocal() as db:
            db.add(
                WebhookDelivery(
                    user_id=user_id,
                    event=event,
                    url=url[:500],
                    success=success,
                    status_code=status_code,
                    error=(error or "")[:300] or None,
                )
            )
            await db.commit()
    except Exception:
        pass


def _build_payload(url: str, event: str, data: dict) -> dict:
    text = _format_text(event, data)
    if "hooks.slack.com" in url:
        return {"text": text}
    if "discord.com/api/webhooks" in url:
        color = {"analysis_complete": 0x6366F1, "trade_executed": 0x10B981, "alert_triggered": 0xF59E0B}.get(
            event, 0x6B7280
        )
        return {"embeds": [{"title": _event_title(event), "description": text, "color": color}]}
    if "api.telegram.org" in url:
        return {"text": f"{_event_title(event)}\n\n{text}", "disable_web_page_preview": True}
    return {"event": event, "data": data, "text": text}


def _event_title(event: str) -> str:
    return {
        "analysis_complete": "📊 Analysis Complete",
        "trade_executed": "💰 Trade Executed",
        "alert_triggered": "🔔 Price Alert",
        "signal_flip": "🔄 Signal Reversal",
    }.get(event, event)


def _signal_direction(signal: str | None) -> str:
    return signal_direction(signal)


def is_signal_flip(prev_signal: str | None, new_signal: str | None) -> bool:
    """True when the directional stance reversed (bullish↔bearish) or
    when a first directional signal appears from a neutral/unknown state."""
    prev_dir = _signal_direction(prev_signal)
    new_dir = _signal_direction(new_signal)
    if prev_dir == new_dir:
        return False
    return prev_dir == "neutral" or new_dir == "neutral" or {prev_dir, new_dir} == {"bullish", "bearish"}


def _format_text(event: str, data: dict) -> str:
    if event == "analysis_complete":
        return (
            f"**{data.get('ticker', '?')}** — Signal: **{data.get('signal', '?')}**\n"
            f"Date: {data.get('trade_date', '')}\n{data.get('summary', '')[:300]}"
        )
    if event == "trade_executed":
        return (
            f"**{data.get('ticker', '?')}** {data.get('action', '?')} execution\n"
            f"Quantity: {data.get('quantity', 0):.4f} @ ${data.get('price', 0):.2f}"
        )
    if event == "signal_flip":
        return (
            f"🔄 **Signal Reversal** on **{data.get('ticker', '?')}**\n"
            f"Changed from **{data.get('prev_signal', '?')}** to **{data.get('new_signal', '?')}**"
        )
    if event == "alert_triggered":
        alert_type = data.get("alert_type", "price")
        if alert_type == "support":
            return f"🚨 **SUPPORT BREACH** on **{data.get('ticker', '?')}**\nPrice crossed below support level: **${data.get('target_price', 0):.2f}**"
        if alert_type == "resistance":
            return f"🚀 **RESISTANCE BREACH** on **{data.get('ticker', '?')}**\nPrice crossed above resistance level: **${data.get('target_price', 0):.2f}**"
        cond_str = "crossed above" if data.get("condition", "") == "above" else "crossed below"
        return (
            f"🔔 **Price Alert** on **{data.get('ticker', '?')}**\n"
            f"Price {cond_str} target of **${data.get('target_price', 0):.2f}**"
        )
    return json.dumps(data)[:500]


async def resolve_webhook_target(url: str) -> WebhookTarget:
    """Validate *url* and resolve it once to a set of public IP addresses."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not contain credentials")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL is missing a host")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValueError("Webhook URL has an invalid port") from exc

    def _resolve():
        return socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(None, _resolve)
    except socket.gaierror:
        raise ValueError("Webhook host could not be resolved") from None

    addresses: list[str] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError as exc:
            raise ValueError("Webhook host resolved to an invalid address") from exc
        if not ip.is_global:
            raise ValueError("Webhook URL resolves to a disallowed internal address")
        normalized = str(ip)
        if normalized not in addresses:
            addresses.append(normalized)

    if not addresses:
        raise ValueError("Webhook host could not be resolved")
    return WebhookTarget(url=url, host=host, port=port, addresses=tuple(addresses))


def _normalized_host(host: str) -> str:
    return host.rstrip(".").lower()


class _PinnedWebhookNetworkBackend:
    """httpcore network backend that dials only a pre-vetted address list."""

    def __init__(self, target: WebhookTarget) -> None:
        import httpcore

        self._target = target
        self._backend = httpcore.AnyIOBackend()
        self._next_address = 0

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        import httpcore

        if _normalized_host(host) != _normalized_host(self._target.host) or port != self._target.port:
            raise httpcore.ConnectError("Pinned webhook transport rejected an unexpected destination")
        address = self._target.addresses[self._next_address % len(self._target.addresses)]
        self._next_address += 1
        return await self._backend.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        import httpcore

        raise httpcore.ConnectError("Pinned webhook transport does not allow Unix sockets")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


def _pinned_webhook_transport(target: WebhookTarget):
    """Return an httpx transport that preserves Host/SNI but pins TCP IPs.

    httpx/httpcore derives HTTP Host and TLS SNI from the request URL, which
    remains ``target.url``. Replacing only its network backend therefore
    connects to a vetted numeric address without disabling certificate
    validation or sending an IP-based Host header.
    """
    import httpx

    transport = httpx.AsyncHTTPTransport(
        trust_env=False,
        retries=0,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
    )
    pool = getattr(transport, "_pool", None)
    if pool is None or not hasattr(pool, "_network_backend"):
        raise RuntimeError("Installed httpx/httpcore does not support pinned webhook transport")
    pool._network_backend = _PinnedWebhookNetworkBackend(target)
    return transport


def _webhook_client(target: WebhookTarget):
    import httpx

    return httpx.AsyncClient(
        transport=_pinned_webhook_transport(target),
        timeout=10.0,
        follow_redirects=False,
        trust_env=False,
    )


def _retry_after_seconds(response) -> float | None:
    """Return a bounded Retry-After delay in seconds, if the header is valid."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None

    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at - datetime.now(UTC)).total_seconds()

    return min(_MAX_RETRY_AFTER_SECONDS, max(0.0, seconds))


def _webhook_retry_wait(retry_state: RetryCallState) -> float:
    """Honor Retry-After, otherwise use full-jitter exponential backoff."""
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome is not None else None
    if isinstance(exc, _RetryableWebhookResponse) and exc.retry_after is not None:
        return exc.retry_after

    ceiling = float(2 ** max(0, retry_state.attempt_number - 1))
    return random.uniform(0.0, ceiling)


async def test_webhook_url(url: str) -> bool:
    import httpx

    from backend.core.log_redaction import register_sensitive_literal

    register_sensitive_literal(url)
    payload = {
        "text": "TradingAgents webhook testi başarılı! ✓",
        "content": "TradingAgents webhook testi başarılı! ✓",
    }
    try:
        target = await resolve_webhook_target(url)
        async with _webhook_client(target) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                return False
            return True
    except (httpx.RequestError, ValueError):
        return False


async def send_webhook(
    url: str,
    event: str,
    data: dict,
    retries: int = 2,
    user_id: int | None = None,
) -> bool:
    if not url:
        return False
    from backend.core.log_redaction import register_sensitive_literal

    register_sensitive_literal(url)
    result = False
    last_status_code: int | None = None
    last_error: str | None = None
    try:
        import httpx

        # Resolve and vet the destination exactly once. Every retry reuses the
        # same pinned target/transport, so retrying cannot reopen a DNS-rebinding
        # window after the security check has passed.
        target = await resolve_webhook_target(url)
        payload = _build_payload(url, event, data)
        attempts = max(1, retries + 1)
        async with _webhook_client(target) as client:
            retrying = AsyncRetrying(
                stop=stop_after_attempt(attempts),
                retry=retry_if_exception_type(_RetryableWebhookError),
                wait=_webhook_retry_wait,
                reraise=True,
            )
            try:
                async for attempt in retrying:
                    with attempt:
                        try:
                            response = await client.post(url, json=payload)
                        except httpx.RequestError as exc:
                            last_error = str(exc)
                            raise _RetryableWebhookError(str(exc)) from exc

                        last_status_code = response.status_code
                        if response.status_code < 300:
                            result = True
                            break
                        if response.status_code in _RETRYABLE_WEBHOOK_STATUSES:
                            raise _RetryableWebhookResponse(
                                response.status_code,
                                retry_after=_retry_after_seconds(response),
                            )
                        # Redirects and permanent client/server responses are
                        # not retried. Redirect following stays disabled so the
                        # vetted destination cannot be swapped underneath us.
                        break
            except _RetryableWebhookError as exc:
                if last_error is None and not isinstance(exc, _RetryableWebhookResponse):
                    last_error = str(exc)
    except Exception as exc:
        _logger.warning("Webhook failed: %s", exc)
        last_error = str(exc)

    if user_id is not None:
        task = asyncio.create_task(_log_delivery(user_id, event, url, result, last_status_code, last_error))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    return result


async def notify_analysis_complete(
    ticker: str, signal: str | None, trade_date: str, final_decision: str, settings
) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _enabled_webhook_events(settings)
    if "analysis_complete" not in events or not url:
        return
    user_id = getattr(settings, "user_id", None)
    await send_webhook(
        url,
        "analysis_complete",
        {
            "ticker": ticker,
            "signal": signal,
            "trade_date": trade_date,
            "summary": (final_decision or "")[:300],
        },
        user_id=user_id,
    )


async def notify_trade_executed(ticker: str, action: str, quantity: float, price: float, settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _enabled_webhook_events(settings)
    if "trade_executed" not in events or not url:
        return
    user_id = getattr(settings, "user_id", None)
    await send_webhook(
        url,
        "trade_executed",
        {"ticker": ticker, "action": action, "quantity": quantity, "price": price},
        user_id=user_id,
    )


async def notify_alert_triggered(
    ticker: str,
    condition: str,
    target_price: float,
    settings,
    alert_type: str = "price",
    market_summary: str = "",
) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _enabled_webhook_events(settings)
    if "alert_triggered" not in events or not url:
        return
    user_id = getattr(settings, "user_id", None)
    payload = {"ticker": ticker, "condition": condition, "target_price": target_price, "alert_type": alert_type}
    if market_summary:
        payload["market_summary"] = market_summary
    await send_webhook(url, "alert_triggered", payload, user_id=user_id)


async def notify_signal_flip(ticker: str, prev_signal: str | None, new_signal: str | None, settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    if not is_signal_flip(prev_signal, new_signal):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _enabled_webhook_events(settings)
    if "signal_flip" not in events or not url:
        return
    user_id = getattr(settings, "user_id", None)
    await send_webhook(
        url,
        "signal_flip",
        {"ticker": ticker, "prev_signal": prev_signal, "new_signal": new_signal},
        user_id=user_id,
    )


def _enabled_webhook_events(settings) -> list[str]:
    """Return a validated native event list, failing closed for corrupt rows.

    ``webhook_events`` is normalized to JSON by the settings migration. Do
    not reintroduce old comma/JSON-string parsers here: malformed manual data
    should disable delivery until it is fixed rather than silently guessing.
    """
    events = getattr(settings, "webhook_events", [])
    if not isinstance(events, list):
        _logger.warning("Invalid webhook_events storage type %s; no webhooks will fire", type(events).__name__)
        return []
    return [event for event in events if isinstance(event, str) and event in WEBHOOK_EVENTS]
