import asyncio
import json
import logging

_logger = logging.getLogger(__name__)


def _build_payload(url: str, event: str, data: dict) -> dict:
    text = _format_text(event, data)
    if "hooks.slack.com" in url:
        return {"text": text}
    if "discord.com/api/webhooks" in url:
        color = {"analysis_complete": 0x6366F1, "trade_executed": 0x10B981, "alert_triggered": 0xF59E0B}.get(
            event, 0x6B7280
        )
        return {"embeds": [{"title": _event_title(event), "description": text, "color": color}]}
    return {"event": event, "data": data, "text": text}


def _event_title(event: str) -> str:
    return {
        "analysis_complete": "📊 Analysis Complete",
        "trade_executed": "💰 Trade Executed",
        "alert_triggered": "🔔 Price Alert",
    }.get(event, event)


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
    if event == "alert_triggered":
        alert_type = data.get("alert_type", "price")
        if alert_type == "support":
            return f"🚨 **SUPPORT BREACH** on **{data.get('ticker', '?')}**\nPrice crossed below support level: **${data.get('target_price', 0):.2f}**"
        elif alert_type == "resistance":
            return f"🚀 **RESISTANCE BREACH** on **{data.get('ticker', '?')}**\nPrice crossed above resistance level: **${data.get('target_price', 0):.2f}**"
        else:
            cond_str = "crossed above" if data.get('condition', '') == 'above' else "crossed below"
            return (
                f"🔔 **Price Alert** on **{data.get('ticker', '?')}**\n"
                f"Price {cond_str} target of **${data.get('target_price', 0):.2f}**"
            )
    return json.dumps(data)[:500]


async def send_webhook(url: str, event: str, data: dict, retries: int = 2) -> bool:
    if not url:
        return False
    try:
        import httpx

        payload = _build_payload(url, event, data)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(retries + 1):
                try:
                    r = await client.post(url, json=payload)
                    if r.status_code < 300:
                        return True
                    if attempt < retries:
                        await asyncio.sleep(2**attempt)
                except httpx.RequestError:
                    if attempt < retries:
                        await asyncio.sleep(2**attempt)
        return False
    except Exception as exc:
        _logger.debug("Webhook failed: %s", exc)
        return False


async def notify_analysis_complete(
    ticker: str, signal: str | None, trade_date: str, final_decision: str, settings
) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "analysis_complete" not in events or not url:
        return
    await send_webhook(
        url,
        "analysis_complete",
        {
            "ticker": ticker,
            "signal": signal,
            "trade_date": trade_date,
            "summary": (final_decision or "")[:300],
        },
    )


async def notify_trade_executed(ticker: str, action: str, quantity: float, price: float, settings) -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "trade_executed" not in events or not url:
        return
    await send_webhook(
        url, "trade_executed", {"ticker": ticker, "action": action, "quantity": quantity, "price": price}
    )


async def notify_alert_triggered(ticker: str, condition: str, target_price: float, settings, alert_type: str = "price") -> None:
    if not getattr(settings, "webhook_enabled", False):
        return
    url = getattr(settings, "webhook_url", "") or ""
    events = _parse_events(getattr(settings, "webhook_events", "[]"))
    if "alert_triggered" not in events or not url:
        return
    await send_webhook(url, "alert_triggered", {"ticker": ticker, "condition": condition, "target_price": target_price, "alert_type": alert_type})


def _parse_events(raw: str) -> list[str]:
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []
