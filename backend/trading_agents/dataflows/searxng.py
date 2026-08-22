from __future__ import annotations

import logging
import threading
import time

import httpx

logger = logging.getLogger(__name__)
_UA = "tradingagents/0.2 (+https://github.com/JustSadY/TradingAgents)"

# --- Process-wide cooldown for 429 rate limiting ---
_COOLDOWN_SECONDS = 60.0
_cooldown_lock = threading.Lock()
_cooldown_until = 0.0


def _is_cooling_down() -> bool:
    """Return True if the SearXNG source is in a rate-limit cooldown."""
    with _cooldown_lock:
        return _cooldown_until > time.monotonic()


def _start_cooldown() -> None:
    """Activate a process-wide cooldown after a 429 response."""
    global _cooldown_until
    with _cooldown_lock:
        now = time.monotonic()
        if _cooldown_until <= now:
            _cooldown_until = now + _COOLDOWN_SECONDS
            logger.warning(
                "SearXNG rate limited (HTTP 429); cooling down for %.0fs.",
                _COOLDOWN_SECONDS,
            )

def fetch_searxng_results(query: str, base_url: str, limit: int = 10, timeout: float = 8.0) -> str:
    """Query a user-configured SearXNG instance for live web results.

    Raises on any failure (bad URL, connection refused, timeout, unexpected
    payload) so the caller can fall back to another source — most users have
    never stood up a SearXNG instance, so failing fast here matters more than
    a rich error message.
    """
    base = base_url.rstrip("/")
    response = httpx.get(
        f"{base}/search",
        params={"q": query, "format": "json"},
        headers={"User-Agent": _UA, "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        return f"No SearXNG results found for query: {query}"

    lines = [f"## SearXNG results for: {query}"]
    for item in results[:limit]:
        title = item.get("title", "").strip()
        link = item.get("url", "").strip()
        snippet = (item.get("content") or "").replace("\n", " ").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        lines.append(f"- **{title}** ({link})\n  {snippet}")

    return "\n".join(lines)
