import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

_logger = logging.getLogger(__name__)

def _jitter(delay: float, jitter_factor: float = 0.1) -> float:
    return delay * (1.0 + jitter_factor * (2.0 * random.random() - 1.0))

def retry_sync(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int, float], None] | None = None,
) -> T:
    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as exc:
            if attempt < max_retries:
                delay = min(base_delay * (2**attempt), max_delay)
                sleep_time = _jitter(delay, jitter_factor)
                if on_retry:
                    on_retry(exc, attempt + 1, sleep_time)
                else:
                    _logger.warning(
                        "Retry %d/%d after %s: %s",
                        attempt + 1,
                        max_retries,
                        type(exc).__name__,
                        exc,
                    )
                time.sleep(sleep_time)
            else:
                raise

async def retry_async(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int, float], None] | None = None,
) -> T:
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except retryable_exceptions as exc:
            if attempt < max_retries:
                delay = min(base_delay * (2**attempt), max_delay)
                sleep_time = _jitter(delay, jitter_factor)
                if on_retry:
                    on_retry(exc, attempt + 1, sleep_time)
                else:
                    _logger.warning(
                        "Retry %d/%d after %s: %s",
                        attempt + 1,
                        max_retries,
                        type(exc).__name__,
                        exc,
                    )
                await asyncio.sleep(sleep_time)
            else:
                raise
