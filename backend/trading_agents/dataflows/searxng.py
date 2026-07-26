from __future__ import annotations

import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def fetch_searxng_results(query: str, base_url: str, limit: int = 10, timeout: float = 8.0) -> str:
    """Query a user-configured SearXNG instance for live web results.

    Raises on any failure (bad URL, connection refused, timeout, unexpected
    payload) so the caller can fall back to another source — most users have
    never stood up a SearXNG instance, so failing fast here matters more than
    a rich error message.
    """
    base = base_url.rstrip("/")
    url = f"{base}/search?{urlencode({'q': query, 'format': 'json'})}"
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user-configured URL, opt-in feature
        payload = json.loads(resp.read())

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
