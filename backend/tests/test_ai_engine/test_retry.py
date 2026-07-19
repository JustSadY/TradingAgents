import pytest

from backend.trading_agents.dataflows.retry import retry_sync, retry_async


class _RetryableError(ValueError):
    pass


class _FatalError(RuntimeError):
    pass


def test_retry_sync_success_on_first_try():
    assert retry_sync(lambda: 42) == 42


def test_retry_sync_retries_then_succeeds():
    call_count = 0

    def _flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _RetryableError("not yet")
        return "ok"

    result = retry_sync(
        _flaky,
        max_retries=3,
        base_delay=0.01,
        retryable_exceptions=(_RetryableError,),
    )
    assert result == "ok"
    assert call_count == 3


def test_retry_sync_exhausts_retries():
    def _always_fails():
        raise _RetryableError("always")

    with pytest.raises(_RetryableError):
        retry_sync(
            _always_fails,
            max_retries=2,
            base_delay=0.01,
            retryable_exceptions=(_RetryableError,),
        )


def test_retry_sync_non_retryable_exception_propagates():
    def _fatal():
        raise _FatalError("boom")

    with pytest.raises(_FatalError):
        retry_sync(
            _fatal,
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(_RetryableError,),
        )


@pytest.mark.asyncio
async def test_retry_async_success_on_first_try():
    result = await retry_async(lambda: _async_val(42))
    assert result == 42


@pytest.mark.asyncio
async def test_retry_async_exhausts():
    async def _fail():
        raise _RetryableError("async fail")

    with pytest.raises(_RetryableError):
        await retry_async(
            _fail,
            max_retries=1,
            base_delay=0.01,
            retryable_exceptions=(_RetryableError,),
        )


async def _async_val(v):
    return v
