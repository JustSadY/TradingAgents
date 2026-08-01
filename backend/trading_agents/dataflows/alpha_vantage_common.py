import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from backend.trading_agents.dataflows.config import get_config
from backend.trading_agents.dataflows.rate_limiter import TokenBucketRateLimiter
from backend.trading_agents.dataflows.retry import retry_sync

_logger = logging.getLogger(__name__)
API_BASE_URL = "https://www.alphavantage.co/query"

_AV_RATE_LIMITERS: dict[tuple[str, int, float], TokenBucketRateLimiter] = {}
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

def _load_rate_limiter() -> TokenBucketRateLimiter:
    cfg = get_config()
    calls = int(cfg.get("alpha_vantage_rate_limit_calls", 5))
    window = float(cfg.get("alpha_vantage_rate_limit_window", 60.0))
    key = (_credential_scope(), calls, window)
    with _AV_STATE_LOCK:
        limiter = _AV_RATE_LIMITERS.get(key)
        if limiter is None:
            limiter = TokenBucketRateLimiter(calls=calls, window_seconds=window, name="Alpha Vantage")
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

def _make_api_request(function_name: str, params: dict) -> dict | str:
    _load_rate_limiter().acquire_sync()

    def _do_request() -> str:
        api_params = params.copy()
        api_params.update(
            {
                "function": function_name,
                "apikey": get_api_key(),
                "source": "trading_agents",
            }
        )
        response = requests.get(API_BASE_URL, params=api_params, timeout=_REQUEST_TIMEOUT)
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

    cfg = get_config()
    return retry_sync(
        _do_request,
        max_retries=cfg.get("alpha_vantage_retry_attempts", 3),
        base_delay=cfg.get("alpha_vantage_retry_delay", 2.0),
        retryable_exceptions=(requests.RequestException, AlphaVantageRateLimitError, ConnectionError),
    )

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
