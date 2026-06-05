from typing import Annotated
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
    get_sec_filings as get_yfinance_sec_filings,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .utils import safe_ticker_component
from .config import get_config
from .reddit import fetch_reddit_posts
from .stocktwits import fetch_stocktwits_messages
import logging
_logger = logging.getLogger(__name__)
_TICKER_FIRST_METHODS = frozenset({
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_insider_transactions",
    "get_sec_filings",
    "fetch_reddit_posts",
    "fetch_stocktwits_messages",
})
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_sec_filings"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "social_sentiment_data": {
        "description": "Social media sentiment data",
        "tools": [
            "fetch_reddit_posts",
            "fetch_stocktwits_messages",
        ]
    }
}
VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]
VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    "get_sec_filings": {
        "yfinance": get_yfinance_sec_filings,
    },
    "fetch_reddit_posts": {
        "reddit": fetch_reddit_posts,
    },
    "fetch_stocktwits_messages": {
        "stocktwits": fetch_stocktwits_messages,
    },
}
import os
import json
import time
import sqlite3
import threading
from pathlib import Path
class APICache:
    _init_lock = threading.Lock()
    _initialized = False
    @classmethod
    def get_cache_path(cls) -> Path:
        config = get_config()
        cache_dir = Path(config.get("data_cache_dir", os.path.join(os.path.expanduser("~"), ".tradingagents", "cache")))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "api_cache.sqlite3"
    @classmethod
    def _ensure_schema(cls, conn) -> None:
        with cls._init_lock:
            if cls._initialized:
                return
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    method TEXT NOT NULL,
                    ts REAL NOT NULL,
                    data_json TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_method ON api_cache(method)")
            cls._initialized = True
    @classmethod
    def _connect(cls):
        conn = sqlite3.connect(str(cls.get_cache_path()), timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cls._ensure_schema(conn)
        return conn
    @classmethod
    def get_ttl(cls, method: str) -> float:
        try:
            category = get_category_for_method(method)
        except ValueError:
            return 3600.0
        if category == "core_stock_apis" or category == "technical_indicators":
            return 600.0
        elif category == "fundamental_data":
            return 43200.0
        elif category == "news_data" or category == "social_sentiment_data":
            return 1800.0
        return 3600.0
    @classmethod
    def get(cls, method: str, *args, **kwargs):
        key = f"{method}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        ttl = cls.get_ttl(method)
        now = time.time()
        conn = cls._connect()
        try:
            with conn:
                row = conn.execute(
                    "SELECT ts, data_json FROM api_cache WHERE cache_key = ?",
                    (key,),
                ).fetchone()
                if not row:
                    return None
                ts, data_json = row
                if now - float(ts) >= ttl:
                    conn.execute("DELETE FROM api_cache WHERE cache_key = ?", (key,))
                    return None
                return json.loads(data_json)
        finally:
            conn.close()
    @classmethod
    def set(cls, method: str, data, *args, **kwargs) -> None:
        key = f"{method}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        now = time.time()
        conn = cls._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO api_cache(cache_key, method, ts, data_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        ts=excluded.ts,
                        data_json=excluded.data_json,
                        method=excluded.method
                    """,
                    (key, method, now, json.dumps(data)),
                )
                conn.execute("DELETE FROM api_cache WHERE ? - ts > 86400.0", (now,))
        finally:
            conn.close()
def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")
def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")
def route_to_vendor(method: str, *args, **kwargs):
    if method in _TICKER_FIRST_METHODS and args:
        safe_ticker_component(args[0])
    cached_val = APICache.get(method, *args, **kwargs)
    if cached_val is not None:
        return cached_val
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        try:
            val = impl_func(*args, **kwargs)
            APICache.set(method, val, *args, **kwargs)
            return val
        except AlphaVantageRateLimitError:
            continue
    raise RuntimeError(f"No available vendor for '{method}'")
