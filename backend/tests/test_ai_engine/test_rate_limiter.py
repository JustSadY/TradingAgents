import time

import pytest

from backend.trading_agents.dataflows.rate_limiter import TokenBucketRateLimiter

def test_acquire_sync_grants_token():
    limiter = TokenBucketRateLimiter(calls=10, window_seconds=60.0)
    assert limiter.acquire_sync(timeout=1) is True

def test_acquire_sync_exhaustion():
    limiter = TokenBucketRateLimiter(calls=2, window_seconds=60.0)
    assert limiter.acquire_sync(timeout=0.1) is True
    assert limiter.acquire_sync(timeout=0.1) is True
    assert limiter.acquire_sync(timeout=0.1) is False

def test_acquire_sync_refill():
    limiter = TokenBucketRateLimiter(calls=60, window_seconds=60.0)
    for _ in range(60):
        assert limiter.acquire_sync(timeout=0.01) is True
    assert limiter.acquire_sync(timeout=0.01) is False
    time.sleep(1.1)
    assert limiter.acquire_sync(timeout=0.1) is True

@pytest.mark.asyncio
async def test_acquire_async_grants_token():
    limiter = TokenBucketRateLimiter(calls=5, window_seconds=60.0)
    assert await limiter.acquire_async(timeout=1) is True

@pytest.mark.asyncio
async def test_acquire_async_exhaustion():
    limiter = TokenBucketRateLimiter(calls=1, window_seconds=60.0)
    assert await limiter.acquire_async(timeout=0.1) is True
    assert await limiter.acquire_async(timeout=0.1) is False

def test_name_is_optional():
    limiter = TokenBucketRateLimiter(calls=3, window_seconds=60.0, name="Custom")
    assert limiter.acquire_sync(timeout=0.5) is True
