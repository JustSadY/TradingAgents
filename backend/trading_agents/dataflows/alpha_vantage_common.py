"""Shared Alpha Vantage transport.

The three moving parts here — pacing, HTTP and retry — are all handled by
packages this project already depends on rather than by hand:

* ``aiolimiter`` for the calls-per-window budget,
* ``httpx`` for the request (already the app's HTTP client elsewhere),
* ``tenacity`` for backoff, which is also what the agent runtime retries with.

That is why the vendor functions here are coroutines: ``aiolimiter`` is
async-only, and ``route_to_vendor`` already awaits a coroutine vendor directly
instead of pushing it to a thread.
"""

import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from io import StringIO

import httpx
import pandas as pd
from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.trading_agents.dataflows.config import get_config

_logger = logging.getLogger(__name__)
API_BASE_URL = "https://www.alphavantage.co/query"

_AV_RATE_LIMITERS: dict[tuple[str, int, float], AsyncLimiter] = {}
_AV_KEY_INDICES: dict[str, int] = {}
_AV_STATE_LOCK = threading.Lock()

def reset_state() -> None:
    """Clear cached rate limiters and key indices (primarily test support).

    Called by tests and when the global config is re-initialized between runs.
    """
    with _AV_STATE_LOCK:
        _AV_RATE_LIMITERS.clear()
        _AV_KEY_INDICES.clear()

def _credential_scope() -> str:
    raw = get_config().get("alpha_vantage_api_key") or os.getenv("ALPHA_VANTAGE_API_KEY", "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _load_rate_limiter() -> AsyncLimiter:
    """The calls-per-window budget for the credentials currently configured.

    Keyed by credential scope so rotating to a different key set does not
    inherit the previous one's spent budget.
    """
    cfg = get_config()
    calls = int(cfg.get("alpha_vantage_rate_limit_calls", 5))
    window = float(cfg.get("alpha_vantage_rate_limit_window", 60.0))
    key = (_credential_scope(), calls, window)
    with _AV_STATE_LOCK:
        limiter = _AV_RATE_LIMITERS.get(key)
        if limiter is None:
            limiter = AsyncLimiter(calls, window)
            _AV_RATE_LIMITERS[key] = limiter
        return limiter

def _read_api_keys() -> list[str]:
    raw = get_config().get("alpha_vantage_api_key") or os.getenv("ALPHA_VANTAGE_API_KEY", "")
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]

def _rotate_api_key() -> str | None:
    keys = _read_api_keys()
    if len(keys) < 2:
        return None
    scope = _credential_scope()
    with _AV_STATE_LOCK:
        index = (_AV_KEY_INDICES.get(scope, 0) + 1) % len(keys)
        _AV_KEY_INDICES[scope] = index
    _logger.info("Rotated to Alpha Vantage API key %d/%d", index + 1, len(keys))
    return keys[index]

def get_api_key() -> str:
    keys = _read_api_keys()
    if not keys:
        raise ValueError(
            "ALPHA_VANTAGE_API_KEY environment variable is not set. Set a single key or a comma-separated list of keys."
        )
    with _AV_STATE_LOCK:
        index = _AV_KEY_INDICES.get(_credential_scope(), 0)
    return keys[index % len(keys)]

def format_datetime_for_api(date_input) -> str:
    if isinstance(date_input, str):
        if len(date_input) == 13 and "T" in date_input:
            return date_input
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}") from None
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")

class AlphaVantageRateLimitError(Exception):
    pass

_REQUEST_TIMEOUT = 30

_RETRYABLE = (httpx.HTTPError, AlphaVantageRateLimitError, ConnectionError)


async def _do_request(function_name: str, params: dict) -> str:
    api_params = params.copy()
    api_params.update(
        {
            "function": function_name,
            "apikey": get_api_key(),
            "source": "trading_agents",
        }
    )
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        response = await client.get(API_BASE_URL, params=api_params)
    response.raise_for_status()
    response_text = response.text
    try:
        response_json = json.loads(response_text)
        if "Information" in response_json:
            info_message = response_json["Information"]
            if "rate limit" in info_message.lower() or "api key" in info_message.lower():
                _rotate_api_key()
                raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {info_message}")
            if "Invalid API call" in info_message or "invalid" in info_message.lower():
                _rotate_api_key()
    except json.JSONDecodeError:
        pass
    return response_text


async def _make_api_request(function_name: str, params: dict) -> dict | str:
    """One paced, retried Alpha Vantage call.

    The limiter is entered per attempt, not once per call: a retry is another
    request against the same per-minute budget, and spending it outside the
    limiter is how a backoff storm turns into a rate-limit ban.
    """
    cfg = get_config()
    attempts = int(cfg.get("alpha_vantage_retry_attempts", 3))
    delay = float(cfg.get("alpha_vantage_retry_delay", 2.0))
    limiter = _load_rate_limiter()

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts + 1),
        wait=wait_exponential_jitter(initial=delay, max=60.0),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    ):
        with attempt:
            async with limiter:
                return await _do_request(function_name, params)
    raise AssertionError("unreachable: AsyncRetrying either returns or reraises")

def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    if not csv_data or csv_data.strip() == "":
        return csv_data
    try:
        df = pd.read_csv(StringIO(csv_data))
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]
        return filtered_df.to_csv(index=False)
    except Exception as e:
        _logger.warning("Failed to filter CSV data by date range: %s", e)
        return csv_data
