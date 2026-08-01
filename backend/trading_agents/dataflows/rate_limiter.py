import asyncio
import logging
import threading
import time

_logger = logging.getLogger(__name__)

class TokenBucketRateLimiter:
    def __init__(
        self,
        calls: int,
        window_seconds: float = 60.0,
        name: str = "",
    ):
        self.max_tokens = calls
        self.tokens = float(calls)
        self.window_seconds = window_seconds
        self.refill_rate = calls / window_seconds
        self.last_refill = time.monotonic()
        self.name = name
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.max_tokens), self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def acquire_sync(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.05, remaining))
        _logger.warning("%s rate limiter timeout after %.0fs", self.name or "API", timeout)
        return False

    async def acquire_async(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self._async_lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(0.05, remaining))
        _logger.warning("%s rate limiter timeout after %.0fs", self.name or "API", timeout)
        return False
