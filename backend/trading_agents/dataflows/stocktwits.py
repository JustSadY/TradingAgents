from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def fetch_stocktwits_messages(ticker: str, limit: int = 30, timeout: float = 10.0) -> str:
    url = _API.format(ticker=ticker.upper())
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: {type(exc).__name__}>"

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
