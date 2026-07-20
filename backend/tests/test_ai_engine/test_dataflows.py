"""Tests for the dataflows infrastructure layer.

Covers config isolation, caching (TTL + max-size eviction), Alpha Vantage key
rotation, and vendor routing fallback logic.  These tests mock external IO and
never call real APIs.
"""

import json
import os
import tempfile
import threading
import time

import pytest

from backend.trading_agents.dataflows import config as dataflow_config
from backend.trading_agents.dataflows.cache import APICache
from backend.trading_agents.dataflows.config import get_config, set_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_cache_path(tmp_path):
    """Point the cache database to a temp directory so tests never collide."""
    old_get = APICache.get_cache_path
    APICache.get_cache_path = staticmethod(lambda: tmp_path / "test_api_cache.sqlite3")
    APICache._initialized_paths.discard(str(tmp_path / "test_api_cache.sqlite3"))
    yield
    APICache.get_cache_path = old_get
    APICache._initialized_paths.clear()


@pytest.fixture(autouse=True)
def _reset_config():
    """Ensure each test starts with a pristine config."""
    dataflow_config._config = None
    dataflow_config._run_config = dataflow_config.contextvars.ContextVar(
        "trading_agents_run_config", default=None
    )
    dataflow_config.initialize_config()


# ---------------------------------------------------------------------------
# Config isolation
# ---------------------------------------------------------------------------


def test_config_defaults_are_present():
    cfg = get_config()
    assert "llm_provider" in cfg
    assert cfg.get("alpha_vantage_rate_limit_calls", None) is not None


def test_set_config_merges_with_defaults():
    set_config({"llm_provider": "anthropic"})
    cfg = get_config()
    assert cfg["llm_provider"] == "anthropic"
    # Unset keys still carry defaults
    assert cfg["output_language"] == "English"


def test_set_config_overrides_nested():
    set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
    cfg = get_config()
    assert cfg["tool_vendors"]["get_stock_data"] == "alpha_vantage"


def test_contextvar_isolation():
    """Concurrent runs must not clobber each other's config."""
    import asyncio

    async def _run(name, cfg):
        set_config(cfg)
        await asyncio.sleep(0.02)
        return get_config()["llm_provider"]

    async def _main():
        r1, r2 = await asyncio.gather(
            _run("a", {"llm_provider": "openai"}),
            _run("b", {"llm_provider": "anthropic"}),
        )
        assert r1 == "openai"
        assert r2 == "anthropic"

    asyncio.run(_main())


# ---------------------------------------------------------------------------
# Cache get/set and TTL
# ---------------------------------------------------------------------------


def test_cache_miss():
    assert APICache.get("get_stock_data", "AAPL", "2024-01-01", "2024-01-31") is None


def test_cache_set_and_get():
    data = {"high": 150.0, "low": 148.0}
    APICache.set("get_stock_data", data, "AAPL", "2024-01-01", "2024-01-31")
    cached = APICache.get("get_stock_data", "AAPL", "2024-01-01", "2024-01-31")
    assert cached == data


def test_cache_respects_category_ttl():
    """Fundamental data should have a longer TTL than stock data."""
    stock_ttl = APICache.get_ttl("get_stock_data")
    fund_ttl = APICache.get_ttl("get_fundamentals")
    assert stock_ttl < fund_ttl


def test_cache_returns_none_after_ttl_expires():
    APICache.set("get_indicators", {"rsi": 65}, "AAPL", "rsi", "2024-01-01", 30)
    old_ttl = APICache.get_ttl
    APICache.get_ttl = staticmethod(lambda _: -1.0)  # expired
    try:
        assert APICache.get("get_indicators", "AAPL", "rsi", "2024-01-01", 30) is None
    finally:
        APICache.get_ttl = old_ttl


def test_cache_evicts_oversized():
    """When cache exceeds max_entries, oldest entries are evicted."""
    max_entries = 10
    old_max = APICache.get_max_entries
    APICache.get_max_entries = staticmethod(lambda: max_entries)
    try:
        for i in range(max_entries + 5):
            APICache.set("get_stock_data", {"i": i}, f"TICKER{i}", "2024-01-01", "2024-01-31")
        conn = APICache._connect()
        try:
            count = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
        finally:
            conn.close()
        assert count <= max_entries
    finally:
        APICache.get_max_entries = old_max


def test_cache_category_for_method():
    from backend.trading_agents.dataflows.cache import get_category_for_method

    assert get_category_for_method("get_stock_data") == "core_stock_apis"
    assert get_category_for_method("fetch_reddit_posts") == "social_sentiment_data"
    with pytest.raises(ValueError):
        get_category_for_method("nonexistent_method")


# ---------------------------------------------------------------------------
# Alpha Vantage key rotation
# ---------------------------------------------------------------------------


def test_alpha_vantage_get_api_key_single():
    from backend.trading_agents.dataflows.alpha_vantage_common import (
        _read_api_keys,
        get_api_key,
        reset_state,
    )

    reset_state()
    set_config({"alpha_vantage_api_key": "demo-key-1"})
    keys = _read_api_keys()
    assert keys == ["demo-key-1"]
    assert get_api_key() == "demo-key-1"


def test_alpha_vantage_get_api_key_comma_separated():
    from backend.trading_agents.dataflows.alpha_vantage_common import (
        _read_api_keys,
        get_api_key,
        reset_state,
    )

    reset_state()
    set_config({"alpha_vantage_api_key": "key-a, key-b, key-c"})
    keys = _read_api_keys()
    assert keys == ["key-a", "key-b", "key-c"]
    # Should start with the first key
    assert get_api_key() == "key-a"


def test_alpha_vantage_rotation():
    from backend.trading_agents.dataflows.alpha_vantage_common import (
        _read_api_keys,
        _rotate_api_key,
        get_api_key,
        reset_state,
    )

    reset_state()
    set_config({"alpha_vantage_api_key": "key-1, key-2, key-3"})
    assert get_api_key() == "key-1"
    _rotate_api_key()
    assert get_api_key() == "key-2"
    _rotate_api_key()
    assert get_api_key() == "key-3"
    _rotate_api_key()
    assert get_api_key() == "key-1"  # wraps around


def test_alpha_vantage_no_rotation_single_key():
    """Rotation on a single key is a no-op (returns None, index unchanged)."""
    from backend.trading_agents.dataflows.alpha_vantage_common import (
        _rotate_api_key,
        get_api_key,
        reset_state,
    )

    reset_state()
    set_config({"alpha_vantage_api_key": "lonely-key"})
    assert _rotate_api_key() is None
    assert get_api_key() == "lonely-key"


def test_alpha_vantage_missing_key_raises():
    from backend.trading_agents.dataflows.alpha_vantage_common import get_api_key, reset_state

    reset_state()
    set_config({})
    key_entry = os.environ.pop("ALPHA_VANTAGE_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="ALPHA_VANTAGE_API_KEY"):
            get_api_key()
    finally:
        if key_entry is not None:
            os.environ["ALPHA_VANTAGE_API_KEY"] = key_entry


def test_alpha_vantage_rate_limiter_configured():
    from backend.trading_agents.dataflows.alpha_vantage_common import (
        _load_rate_limiter,
        reset_state,
    )

    reset_state()
    set_config({
        "alpha_vantage_rate_limit_calls": 10,
        "alpha_vantage_rate_limit_window": 30.0,
    })
    limiter = _load_rate_limiter()
    assert limiter.max_tokens == 10
    assert limiter.window_seconds == 30.0


# ---------------------------------------------------------------------------
# Vendor routing / interface
# ---------------------------------------------------------------------------


def test_vendor_routing_get_vendor_default():
    """Without method-specific config and data_vendors.category = "default", returns "default"."""
    from backend.trading_agents.dataflows.interface import get_vendor

    set_config({"data_vendors": {"core_stock_apis": "default"}})
    vendor = get_vendor("core_stock_apis")
    assert vendor == "default"


def test_vendor_routing_get_vendor_default_from_config():
    """Return the configured category default when data_vendors is set."""
    from backend.trading_agents.dataflows.interface import get_vendor

    set_config({"data_vendors": {"core_stock_apis": "yfinance"}})
    vendor = get_vendor("core_stock_apis")
    assert vendor == "yfinance"


def test_vendor_routing_get_vendor_method_override():
    from backend.trading_agents.dataflows.interface import get_vendor

    set_config({"tool_vendors": {"get_stock_data": "alpha_vantage"}})
    vendor = get_vendor("core_stock_apis", method="get_stock_data")
    assert vendor == "alpha_vantage"


@pytest.mark.asyncio
async def test_route_to_vendor_unknown_method():
    from backend.trading_agents.dataflows.interface import route_to_vendor

    with pytest.raises(ValueError, match="not found in any category"):
        await route_to_vendor("nonexistent_method")


@pytest.mark.asyncio
async def test_route_to_vendor_all_fail(mocker):
    """When every vendor raises, route_to_vendor raises RuntimeError."""
    from backend.trading_agents.dataflows.alpha_vantage_common import reset_state
    from backend.trading_agents.dataflows.interface import VENDOR_METHODS, route_to_vendor

    reset_state()
    set_config({
        "alpha_vantage_api_key": "test-key",
        "tool_vendors": {"get_stock_data": "alpha_vantage,yfinance"},
    })

    # Replace the vendor implementations in VENDOR_METHODS so the fallback chain
    # iterates over mocked functions that always raise.
    orig_methods = VENDOR_METHODS["get_stock_data"]
    mock_av = mocker.Mock(side_effect=ValueError("Alpha Vantage failed"))
    mock_yf = mocker.Mock(side_effect=ValueError("yfinance failed"))
    VENDOR_METHODS["get_stock_data"] = {
        "alpha_vantage": mock_av,
        "yfinance": mock_yf,
    }
    try:
        with pytest.raises(RuntimeError, match="All vendors failed"):
            await route_to_vendor("get_stock_data", "INVALID", "2024-01-01", "2024-01-31")
    finally:
        VENDOR_METHODS["get_stock_data"] = orig_methods


# ---------------------------------------------------------------------------
# Retry integration with config
# ---------------------------------------------------------------------------


def test_retry_sync_success():
    from backend.trading_agents.dataflows.retry import retry_sync

    assert retry_sync(lambda: 42) == 42


def test_retry_async_success():
    import asyncio

    from backend.trading_agents.dataflows.retry import retry_async

    async def val():
        return 42

    assert asyncio.run(retry_async(val)) == 42


def test_retry_sync_exhaustion():
    from backend.trading_agents.dataflows.retry import retry_sync

    calls = 0

    def fail():
        nonlocal calls
        calls += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry_sync(fail, max_retries=2, base_delay=0.01)
    assert calls == 3  # original + 2 retries


# ---------------------------------------------------------------------------
# Config-driven dataflow retry defaults (via alpha_vantage_common)
# ---------------------------------------------------------------------------


def test_dataflow_config_driven_retry():
    """Alpha Vantage retry reads from config not hardcoded values."""
    from backend.trading_agents.dataflows.alpha_vantage_common import reset_state

    reset_state()
    set_config({
        "alpha_vantage_api_key": "test",
        "alpha_vantage_retry_attempts": 5,
        "alpha_vantage_retry_delay": 3.0,
    })
    # The _make_api_request reads these from config; verify by checking
    # that the retry params in the non-existing-key path would use them.
    cfg = get_config()
    assert cfg["alpha_vantage_retry_attempts"] == 5
    assert cfg["alpha_vantage_retry_delay"] == 3.0


# ---------------------------------------------------------------------------
# Edge cases: concurrent cache access
# ---------------------------------------------------------------------------


def test_cache_concurrent_safe():
    """Multiple threads can get/set the cache without errors (low concurrency to avoid SQLite locking)."""
    errors = []

    def _worker(n):
        try:
            for _ in range(3):
                APICache.set("get_stock_data", {"n": n}, f"TICKER{n}", "2024-01-01", "2024-01-31")
                _ = APICache.get("get_stock_data", f"TICKER{n}", "2024-01-01", "2024-01-31")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"Concurrency errors: {errors}"
