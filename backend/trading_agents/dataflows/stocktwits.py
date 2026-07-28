from __future__ import annotations

import json
import logging
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ACCESS_DENIED_COOLDOWN_SECONDS = 900.0
_RATE_LIMIT_COOLDOWN_SECONDS = 60.0
_cooldown_lock = threading.Lock()
_cooldown_until = 0.0
_cooldown_reason: str | None = None


class StockTwitsUnavailable(str):
    """A visible provider-failure result that must not be cached as data."""


def _active_cooldown() -> tuple[float, str] | None:
    global _cooldown_until, _cooldown_reason

    now = time.monotonic()
    with _cooldown_lock:
        if _cooldown_until <= now:
            _cooldown_until = 0.0
            _cooldown_reason = None
            return None
        return _cooldown_until - now, _cooldown_reason or "provider unavailable"


def _start_cooldown(reason: str, seconds: float) -> bool:
    """Start a provider-wide cooldown and return whether this call created it."""
    global _cooldown_until, _cooldown_reason

    now = time.monotonic()
    with _cooldown_lock:
        if _cooldown_until > now:
            return False
        _cooldown_until = now + seconds
        _cooldown_reason = reason
        return True


def reset_stocktwits_cooldown() -> None:
    """Clear process-local cooldown state (primarily useful in tests)."""
    global _cooldown_until, _cooldown_reason

    with _cooldown_lock:
        _cooldown_until = 0.0
        _cooldown_reason = None


def _unavailable_message(reason: str, retry_after: float) -> StockTwitsUnavailable:
    return StockTwitsUnavailable(f"<stocktwits unavailable: {reason}; retry after roughly {math.ceil(retry_after)}s>")


def fetch_stocktwits_messages(ticker: str, limit: int = 30, timeout: float = 10.0) -> str:
    cooldown = _active_cooldown()
    if cooldown is not None:
        retry_after, reason = cooldown
        logger.debug("StockTwits request for %s skipped during cooldown: %s", ticker, reason)
        return _unavailable_message(reason, retry_after)

    url = _API.format(ticker=ticker.upper())
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except HTTPError as exc:
        if exc.code in (401, 403):
            reason = f"HTTP {exc.code} access denied"
            started = _start_cooldown(reason, _ACCESS_DENIED_COOLDOWN_SECONDS)
            if started:
                logger.warning(
                    "StockTwits denied unauthenticated access (HTTP %s); source cooling down for %.0fs.",
                    exc.code,
                    _ACCESS_DENIED_COOLDOWN_SECONDS,
                )
            return _unavailable_message(reason, _ACCESS_DENIED_COOLDOWN_SECONDS)
        if exc.code == 429:
            reason = "HTTP 429 rate limited"
            started = _start_cooldown(reason, _RATE_LIMIT_COOLDOWN_SECONDS)
            if started:
                logger.warning(
                    "StockTwits rate limited requests; source cooling down for %.0fs.", _RATE_LIMIT_COOLDOWN_SECONDS
                )
            return _unavailable_message(reason, _RATE_LIMIT_COOLDOWN_SECONDS)
        logger.warning("StockTwits fetch failed for %s: HTTP %s", ticker, exc.code)
        return StockTwitsUnavailable(f"<stocktwits unavailable: HTTP {exc.code}>")
    except (URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return StockTwitsUnavailable(f"<stocktwits unavailable: {type(exc).__name__}>")

    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${ticker.upper()}>"

    parsed_lines, stats = _parse_stocktwits_messages(messages, limit)
    summary = _format_stocktwits_summary(stats)

    return summary + "\n\n" + "\n".join(parsed_lines)


def _parse_stocktwits_messages(messages: list, limit: int) -> tuple[list[str], dict[str, int]]:
    """Parse raw messages and track sentiment counts."""
    lines = []
    stats = {"Bullish": 0, "Bearish": 0, "no-label": 0}

    for m in messages[:limit]:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        body = (m.get("body") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None

        tag = "no-label"
        if sentiment in ("Bullish", "Bearish"):
            tag = sentiment

        stats[tag] += 1
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    return lines, stats


def _format_stocktwits_summary(stats: dict[str, int]) -> str:
    """Format the sentiment summary line."""
    bullish = stats["Bullish"]
    bearish = stats["Bearish"]
    unlabeled = stats["no-label"]
    total = sum(stats.values())

    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0

    return (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
