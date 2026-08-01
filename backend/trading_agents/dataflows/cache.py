import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from .config import get_config

_logger = logging.getLogger(__name__)

TOOLS_CATEGORIES = {
    "core_stock_apis": {"description": "OHLCV stock price data", "tools": ["get_stock_data"]},
    "technical_indicators": {"description": "Technical analysis indicators", "tools": ["get_indicators"]},
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": ["get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement", "get_sec_filings"],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
            "get_institutional_holdings",
            "get_catalyst_calendar",
            "get_analyst_ratings",
            "get_short_interest",
            "get_valuation_comparison",
            "get_options_data",
            "get_macro_data",
        ],
    },
    "social_sentiment_data": {
        "description": "Social media sentiment data",
        "tools": [
            "fetch_reddit_posts",
            "fetch_stocktwits_messages",
        ],
    },
}

def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

class APICache:
    _init_lock = threading.Lock()
    _initialized_paths: set[str] = set()

    @classmethod
    def get_cache_path(cls) -> Path:
        config = get_config()
        cache_dir = Path(config.get("data_cache_dir", os.path.join(os.path.expanduser("~"), ".tradingagents", "cache")))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "api_cache.sqlite3"

    @classmethod
    def get_max_entries(cls) -> int:
        config = get_config()
        return int(config.get("api_cache_max_entries", 5000))

    @classmethod
    def _ensure_schema(cls, conn, path: str) -> None:
        with cls._init_lock:
            if path in cls._initialized_paths:
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_ts ON api_cache(ts)")
            cls._initialized_paths.add(path)

    @classmethod
    def _connect(cls):
        path = str(cls.get_cache_path())
        conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        cls._ensure_schema(conn, path)
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

    @staticmethod
    def _cache_key(method: str, args: tuple, kwargs: dict, cache_scope: str | None) -> str:
        """Build a stable key, optionally partitioned by a data-source scope.

        The same method/ticker can legitimately yield a different payload for
        different vendor selections.  Keeping that selection outside the key
        made one user's configured provider silently override another's.
        """
        scope = cache_scope or "default"
        return f"{scope}:{method}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"

    @classmethod
    def get(cls, method: str, *args, cache_scope: str | None = None, **kwargs):
        key = cls._cache_key(method, args, kwargs, cache_scope)
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
    def set(cls, method: str, data, *args, cache_scope: str | None = None, **kwargs) -> None:
        key = cls._cache_key(method, args, kwargs, cache_scope)
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
                cls._evict_if_oversized(conn)
        finally:
            conn.close()

    @classmethod
    def _evict_if_oversized(cls, conn) -> None:
        """Delete oldest entries when the cache exceeds ``get_max_entries()``."""
        max_entries = cls.get_max_entries()
        count_row = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()
        if count_row and count_row[0] > max_entries:
            excess = count_row[0] - max_entries
            conn.execute(
                """
                DELETE FROM api_cache WHERE cache_key IN (
                    SELECT cache_key FROM api_cache ORDER BY ts ASC LIMIT ?
                )
                """,
                (excess,),
            )

    @classmethod
    def clear_method_cache(cls, method: str) -> None:
        conn = cls._connect()
        try:
            with conn:
                conn.execute("DELETE FROM api_cache WHERE method = ?", (method,))
        finally:
            conn.close()

    @classmethod
    def clear_category_cache(cls, category: str) -> None:
        try:
            methods = TOOLS_CATEGORIES[category]["tools"]
        except KeyError:
            return
        conn = cls._connect()
        try:
            placeholders = ",".join("?" * len(methods))
            with conn:
                conn.execute(f"DELETE FROM api_cache WHERE method IN ({placeholders})", methods)
        finally:
            conn.close()

    @classmethod
    def evict_stale(cls, max_age: float | None = None) -> int:
        if max_age is None:
            max_age = 86400.0
        now = time.time()
        cutoff = now - max_age
        conn = cls._connect()
        try:
            with conn:
                result = conn.execute("DELETE FROM api_cache WHERE ts < ?", (cutoff,))
                return result.rowcount
        finally:
            conn.close()
