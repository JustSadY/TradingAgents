import asyncio
import json
import logging

_logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task] = set()


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
        pass  # never crash the caller


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
        # Telegram Bot API sendMessage. Configure the URL as
        # https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>
        # — chat_id rides in the query string; the message body carries the text.
        return {"text": f"{_event_title(event)}\n\n{text}", "disable_web_page_preview": True}
    return {"event": event, "data": data, "text": text}


def _event_title(event: str) -> str:
    return {
        "analysis_complete": "📊 Analysis Complete",
        "trade_executed": "💰 Trade Executed",
        "alert_triggered": "🔔 Price Alert",
        "signal_flip": "🔄 Signal Reversal",
    }.get(event, event)


_BULLISH = {"buy", "overweight"}
_BEARISH = {"sell", "underweight"}


def _signal_direction(signal: str | None) -> str:
    s = (signal or "").strip().lower()
    if s in _BULLISH:
        return "bullish"
    if s in _BEARISH:
        return "bearish"
    return "neutral"


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
        elif alert_type == "resistance":
            return f"🚀 **RESISTANCE BREACH** on **{data.get('ticker', '?')}**\nPrice crossed above resistance level: **${data.get('target_price', 0):.2f}**"
        else:
            cond_str = "crossed above" if data.get("condition", "") == "above" else "crossed below"
            return (
                f"🔔 **Price Alert** on **{data.get('ticker', '?')}**\n"
                f"Price {cond_str} target of **${data.get('target_price', 0):.2f}**"
            )
    return json.dumps(data)[:500]


async def send_webhook(
    url: str,
    event: str,
    data: dict,
    retries: int = 2,
    user_id: int | None = None,
) -> bool:
    if not url:
        return False
    result = False
    last_status_code: int | None = None
    last_error: str | None = None
    try:
        import httpx

        payload = _build_payload(url, event, data)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(retries + 1):
                try:
                    r = await client.post(url, json=payload)
                    last_status_code = r.status_code
                    if r.status_code < 300:
                        result = True
                        break
                    if attempt < retries:
                        await asyncio.sleep(2**attempt)
                except httpx.RequestError as exc:
                    last_error = str(exc)
                    if attempt < retries:
                        await asyncio.sleep(2**attempt)
    except Exception as exc:
        _logger.debug("Webhook failed: %s", exc)
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
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
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
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
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
    ticker: str, condition: str, target_price: float, settings, alert_type: str = "price", market_summary: str = ""
) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
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
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "signal_flip" not in events or not url:
        return
    user_id = getattr(settings, "user_id", None)
    await send_webhook(
        url,
        "signal_flip",
        {"ticker": ticker, "prev_signal": prev_signal, "new_signal": new_signal},
        user_id=user_id,
    )


def _parse_events(raw: str) -> list[str]:
    """Parse webhook_events — accepts both JSON array and legacy comma-separated formats."""
    if not raw:
        return []
    stripped = raw.strip()
    # JSON array: '["a","b"]'
    if stripped.startswith("["):
        try:
            result = json.loads(stripped)
            return result if isinstance(result, list) else []
        except Exception:
            pass
    # Anything that looks like a JSON object (starts with '{') is malformed — fail closed.
    if stripped.startswith("{"):
        _logger.warning("Malformed webhook_events value, no webhooks will fire: %.50s", stripped)
        return []
    # Legacy comma-separated: "analysis_complete,trade_executed"
    return [p.strip() for p in stripped.split(",") if p.strip()]
