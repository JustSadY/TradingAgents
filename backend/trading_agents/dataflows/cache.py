"""Bounded on-disk cache for vendor API responses.

Storage is `diskcache`: a SQLite-backed, process- and thread-safe key/value
store. It replaces a hand-written SQLite layer that carried its own schema
creation, WAL/PRAGMA setup, per-path init guards and eviction SQL — roughly a
hundred lines whose only job was to be a cache correctly.

What stays here is the part that is about *this* application: which tool
belongs to which category, how long each category stays fresh, and the ability
to invalidate by method or category rather than by key.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

import diskcache

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
    _stores: dict[str, diskcache.Cache] = {}
    _store_lock = threading.Lock()

    @classmethod
    def get_cache_path(cls) -> Path:
        config = get_config()
        cache_dir = Path(config.get("data_cache_dir", os.path.join(os.path.expanduser("~"), ".tradingagents", "cache")))
        return cache_dir / "api_cache"

    @classmethod
    def get_max_entries(cls) -> int:
        config = get_config()
        return int(config.get("api_cache_max_entries", 5000))

    @classmethod
    def _store(cls) -> diskcache.Cache:
        path = str(cls.get_cache_path())
        store = cls._stores.get(path)
        if store is not None:
            return store
        with cls._store_lock:
            store = cls._stores.get(path)
            if store is None:
                Path(path).mkdir(parents=True, exist_ok=True)
                store = diskcache.Cache(path)
                cls._stores[path] = store
            return store

    @classmethod
    def close(cls) -> None:
        """Release every open store. Tests use this between temp directories."""
        with cls._store_lock:
            for store in cls._stores.values():
                store.close()
            cls._stores.clear()

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

        The method leads the key so invalidating one method (or a category of
        them) is a prefix scan; the store has no secondary index.
        """
        scope = cache_scope or "default"
        return f"{method}\x1f{scope}\x1f{json.dumps(args, sort_keys=True)}\x1f{json.dumps(kwargs, sort_keys=True)}"

    @staticmethod
    def _method_prefix(method: str) -> str:
        return f"{method}\x1f"

    @classmethod
    def get(cls, method: str, *args, cache_scope: str | None = None, **kwargs):
        """Return the cached payload, or ``None`` when missing or stale.

        Freshness is judged on read against the *current* TTL rather than one
        frozen at write time, so shortening a category's TTL takes effect for
        entries already on disk.
        """
        key = cls._cache_key(method, args, kwargs, cache_scope)
        entry = cls._store().get(key)
        if not isinstance(entry, tuple) or len(entry) != 2:
            return None
        ts, data = entry
        if time.time() - float(ts) >= cls.get_ttl(method):
            cls._store().delete(key)
            return None
        return data

    @classmethod
    def set(cls, method: str, data, *args, cache_scope: str | None = None, **kwargs) -> None:
        key = cls._cache_key(method, args, kwargs, cache_scope)
        store = cls._store()
        # A day is the outer bound for anything in here; the per-category TTL
        # in `get` is what actually decides freshness.
        store.set(key, (time.time(), data), expire=86_400.0)
        cls._trim_to_max_entries()

    @classmethod
    def _trim_to_max_entries(cls) -> None:
        """Drop the oldest entries once the store exceeds its entry budget.

        `diskcache` bounds itself by bytes; this cache's configured limit has
        always been a row count, so the count is enforced here.
        """
        store = cls._store()
        excess = len(store) - cls.get_max_entries()
        if excess <= 0:
            return
        aged = []
        for key in list(store.iterkeys()):
            entry = store.get(key)
            if isinstance(entry, tuple) and len(entry) == 2:
                aged.append((float(entry[0]), key))
        aged.sort()
        for _ts, key in aged[:excess]:
            store.delete(key)

    @classmethod
    def clear_method_cache(cls, method: str) -> None:
        store = cls._store()
        prefix = cls._method_prefix(method)
        for key in list(store.iterkeys()):
            if isinstance(key, str) and key.startswith(prefix):
                store.delete(key)

    @classmethod
    def clear_category_cache(cls, category: str) -> None:
        try:
            methods = TOOLS_CATEGORIES[category]["tools"]
        except KeyError:
            return
        for method in methods:
            cls.clear_method_cache(method)

    @classmethod
    def evict_stale(cls, max_age: float | None = None) -> int:
        if max_age is None:
            max_age = 86_400.0
        cutoff = time.time() - max_age
        store = cls._store()
        store.expire()
        removed = 0
        for key in list(store.iterkeys()):
            entry = store.get(key)
            if isinstance(entry, tuple) and len(entry) == 2 and float(entry[0]) < cutoff:
                if store.delete(key):
                    removed += 1
        return removed
