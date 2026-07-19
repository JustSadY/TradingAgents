import json
import logging
import os
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from backend.trading_agents.dataflows.config import get_config
from backend.trading_agents.dataflows.rate_limiter import TokenBucketRateLimiter
from backend.trading_agents.dataflows.retry import retry_sync

_logger = logging.getLogger(__name__)
API_BASE_URL = "https://www.alphavantage.co/query"

# Alpha Vantage free tier: 5 calls per minute.
_AV_RATE_LIMITER = TokenBucketRateLimiter(calls=5, window_seconds=60.0, name="Alpha Vantage")


def get_api_key() -> str:
    api_key = get_config().get("alpha_vantage_api_key") or os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY environment variable is not set.")
    return api_key


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


def _make_api_request(function_name: str, params: dict) -> dict | str:
    _AV_RATE_LIMITER.acquire_sync()

    def _do_request() -> str:
        api_params = params.copy()
        api_params.update(
            {
                "function": function_name,
                "apikey": get_api_key(),
                "source": "trading_agents",
            }
        )
        response = requests.get(API_BASE_URL, params=api_params)
        response.raise_for_status()
        response_text = response.text
        try:
            response_json = json.loads(response_text)
            if "Information" in response_json:
                info_message = response_json["Information"]
                if "rate limit" in info_message.lower() or "api key" in info_message.lower():
                    raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {info_message}")
        except json.JSONDecodeError:
            pass
        return response_text

    return retry_sync(
        _do_request,
        max_retries=3,
        base_delay=2.0,
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
