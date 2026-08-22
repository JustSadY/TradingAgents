from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)
_API = "https://api.alternative.me/fng/?limit=1&format=json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

def fetch_crypto_fear_greed_index(timeout: float = 10.0) -> str:
    """Fetch the current Crypto Fear & Greed Index (alternative.me, free, no API key)."""
    try:
        response = httpx.get(
            _API,
            headers={"User-Agent": _UA, "Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Crypto Fear & Greed fetch failed: %s", exc)
        return "<crypto fear and greed index unavailable>"

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not entries:
        return "<crypto fear and greed index unavailable>"

    entry = entries[0]
    value = entry.get("value", "?")
    classification = entry.get("value_classification", "Unknown")
    return f"Fear and Greed Index: {value} ({classification})"
