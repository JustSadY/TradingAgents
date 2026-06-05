import os
import json
import time
import sqlite3
import threading
import logging
from pathlib import Path
from .config import get_config

_logger = logging.getLogger(__name__)

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

def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

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
