"""Characterization tests for ``resilience.retry_call``.

``retry_call`` is the single retry authority for the whole agent runtime, and
most of its behaviour lived only in the implementation: five separate
non-retryable conditions, the backoff schedule, the per-attempt timeout and the
metrics/WebSocket side effects. These tests pin that behaviour so the
implementation can be rewritten without changing what it does.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.trading_agents.agents.runtime import resilience


@pytest.fixture
def captured_sleeps(monkeypatch):
    """Record backoff delays without actually waiting for them."""
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return sleeps


def _counting(*results):
    """Build a callable returning/raising each of *results* in turn."""
    calls = {"n": 0}

    async def fn():
        index = calls["n"]
        calls["n"] += 1
        outcome = results[min(index, len(results) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    return fn, calls


class TestRetryCallSucceeds:
    async def test_returns_immediately_without_sleeping(self, captured_sleeps):
        fn, calls = _counting("ok")
        result = await resilience.retry_call(fn, label="t", attempts=3, base_delay=1.0)
        assert result == "ok"
        assert calls["n"] == 1
        assert captured_sleeps == []

    async def test_retries_a_transient_failure_then_succeeds(self, captured_sleeps):
        fn, calls = _counting(ConnectionError("boom"), "ok")
        result = await resilience.retry_call(fn, label="t", attempts=3, base_delay=1.0)
        assert result == "ok"
        assert calls["n"] == 2
        assert len(captured_sleeps) == 1
        assert 0.0 <= captured_sleeps[0] <= 1.0

    async def test_backoff_ceiling_doubles_between_attempts(self, captured_sleeps):
        """Delays are jittered, so assert the envelope rather than exact values.

        Full jitter draws uniformly from ``[0, base * 2 ** attempt]``, so the
        ceiling still doubles while concurrent callers stop retrying in lockstep.
        """
        fn, _ = _counting(ConnectionError("boom"))
        with pytest.raises(ConnectionError):
            await resilience.retry_call(fn, label="t", attempts=4, base_delay=2.0)

        assert len(captured_sleeps) == 3
        for delay, ceiling in zip(captured_sleeps, [2.0, 4.0, 8.0], strict=True):
            assert 0.0 <= delay <= ceiling

    async def test_zero_base_delay_stays_exactly_zero(self, captured_sleeps):
        fn, _ = _counting(ConnectionError("boom"))
        with pytest.raises(ConnectionError):
            await resilience.retry_call(fn, label="t", attempts=3, base_delay=0.0)
        assert captured_sleeps == [0.0, 0.0]

    async def test_concurrent_callers_do_not_retry_in_lockstep(self, captured_sleeps):
        """The reason jitter is here at all.

        Analysts run concurrently, so a provider rate limit fails many calls at
        once. Without jitter every one of them would sleep the identical
        interval and hit the provider again as a single burst.
        """
        for _ in range(20):
            fn, _ = _counting(ConnectionError("boom"), "ok")
            await resilience.retry_call(fn, label="t", attempts=2, base_delay=4.0)

        assert len(set(captured_sleeps)) > 1, "all retries drew the same delay"
        assert all(0.0 <= d <= 4.0 for d in captured_sleeps)

    async def test_raises_the_last_exception_when_attempts_run_out(self, captured_sleeps):
        final = ConnectionError("third")
        fn, calls = _counting(ConnectionError("first"), ConnectionError("second"), final)
        with pytest.raises(ConnectionError) as excinfo:
            await resilience.retry_call(fn, label="t", attempts=3, base_delay=0.5)
        assert excinfo.value is final
        assert calls["n"] == 3


class TestRetryCallStopsEarly:
    """The five conditions that must not be retried."""

    async def test_non_transient_error_is_not_retried(self, captured_sleeps):
        fn, calls = _counting(ValueError("bad request"))
        with pytest.raises(ValueError):
            await resilience.retry_call(fn, label="t", attempts=5, base_delay=1.0)
        assert calls["n"] == 1
        assert captured_sleeps == []

    async def test_retry_all_overrides_the_transient_check(self, captured_sleeps):
        fn, calls = _counting(ValueError("bad request"), "ok")
        result = await resilience.retry_call(
            fn, label="t", attempts=3, base_delay=1.0, retry_all=True
        )
        assert result == "ok"
        assert calls["n"] == 2

    async def test_quota_exhausted_stops_immediately(self, captured_sleeps):
        fn, calls = _counting(RuntimeError("Quota exhausted for this project"))
        with pytest.raises(RuntimeError):
            await resilience.retry_call(
                fn, label="t", attempts=5, base_delay=1.0, retry_all=True
            )
        assert calls["n"] == 1
        assert captured_sleeps == []

    async def test_resource_exhausted_with_quota_stops_immediately(self, captured_sleeps):
        fn, calls = _counting(RuntimeError("ResourceExhausted: total quota reached"))
        with pytest.raises(RuntimeError):
            await resilience.retry_call(
                fn, label="t", attempts=5, base_delay=1.0, retry_all=True
            )
        assert calls["n"] == 1

    async def test_resource_exhausted_without_quota_or_total_still_retries(self, captured_sleeps):
        # Narrow match: a plain ResourceExhausted is a rate limit, not a dead quota.
        fn, calls = _counting(RuntimeError("ResourceExhausted: slow down"), "ok")
        result = await resilience.retry_call(
            fn, label="t", attempts=3, base_delay=1.0, retry_all=True
        )
        assert result == "ok"
        assert calls["n"] == 2

    async def test_degraded_provider_function_stops_immediately(self, captured_sleeps):
        fn, calls = _counting(RuntimeError("Degraded function cannot be invoked"))
        with pytest.raises(RuntimeError):
            await resilience.retry_call(
                fn, label="t", attempts=5, base_delay=1.0, retry_all=True
            )
        assert calls["n"] == 1

    async def test_timeout_is_retried_by_default(self, captured_sleeps):
        fn, calls = _counting(TimeoutError("slow"), "ok")
        result = await resilience.retry_call(fn, label="t", attempts=3, base_delay=1.0)
        assert result == "ok"
        assert calls["n"] == 2

    async def test_timeout_is_not_retried_when_the_caller_opts_out(self, captured_sleeps):
        fn, calls = _counting(TimeoutError("slow"))
        with pytest.raises(TimeoutError):
            await resilience.retry_call(
                fn, label="t", attempts=5, base_delay=1.0, retry_timeouts=False
            )
        assert calls["n"] == 1


class TestRetryCallCancellation:
    async def test_cancellation_propagates_without_being_retried(self, captured_sleeps):
        """A cancelled analysis must stop at once.

        ``CancelledError`` is a ``BaseException``, so the retry loop has to let
        it through rather than treating it as a failed attempt — retrying it
        would delay the user's cancellation and re-issue provider calls after
        they asked to stop.
        """
        calls = {"n": 0}

        async def fn():
            calls["n"] += 1
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await resilience.retry_call(fn, label="t", attempts=5, base_delay=1.0, retry_all=True)
        assert calls["n"] == 1
        assert captured_sleeps == []

    async def test_a_non_exception_baseexception_is_not_retried(self, captured_sleeps):
        """Same rule as cancellation, for any other ``BaseException``.

        Uses a locally defined class rather than ``KeyboardInterrupt``, which
        pytest intercepts to abort the whole session.
        """

        class Abort(BaseException):
            pass

        calls = {"n": 0}

        async def fn():
            calls["n"] += 1
            raise Abort()

        with pytest.raises(Abort):
            await resilience.retry_call(fn, label="t", attempts=5, base_delay=1.0, retry_all=True)
        assert calls["n"] == 1


class TestRetryCallTimeout:
    async def test_a_hung_call_is_cut_off_and_retried(self, monkeypatch):
        real_sleep = asyncio.sleep
        sleeps: list[float] = []

        async def fake_sleep(delay):
            sleeps.append(delay)

        calls = {"n": 0}

        async def fn():
            calls["n"] += 1
            if calls["n"] == 1:
                await real_sleep(5)
            return "ok"

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        result = await resilience.retry_call(
            fn, label="t", attempts=2, base_delay=1.0, timeout=0.01
        )
        assert result == "ok"
        assert calls["n"] == 2

    async def test_timeout_multiplier_scales_the_budget(self, monkeypatch):
        real_sleep = asyncio.sleep
        monkeypatch.setattr(asyncio, "sleep", lambda _d: real_sleep(0))

        async def fn():
            await real_sleep(0.05)
            return "ok"

        # 0.01 * 20 = 0.2s budget, comfortably above the 0.05s the call takes.
        result = await resilience.retry_call(
            fn, label="t", attempts=1, base_delay=0, timeout=0.01, timeout_multiplier=20
        )
        assert result == "ok"

    async def test_zero_timeout_disables_the_deadline(self, monkeypatch):
        real_sleep = asyncio.sleep
        monkeypatch.setattr(asyncio, "sleep", lambda _d: real_sleep(0))

        async def fn():
            await real_sleep(0.02)
            return "ok"

        result = await resilience.retry_call(fn, label="t", attempts=1, timeout=0)
        assert result == "ok"


class TestRetryCallExecution:
    async def test_runs_a_blocking_callable_off_the_event_loop(self, captured_sleeps):
        seen: list[str] = []

        def blocking():
            seen.append("ran")
            return "ok"

        result = await resilience.retry_call(
            blocking, label="t", attempts=1, run_in_thread=True
        )
        assert result == "ok"
        assert seen == ["ran"]

    async def test_accepts_a_plain_sync_callable(self, captured_sleeps):
        result = await resilience.retry_call(lambda: "ok", label="t", attempts=1)
        assert result == "ok"

    async def test_attempts_below_one_still_runs_once(self, captured_sleeps):
        fn, calls = _counting("ok")
        assert await resilience.retry_call(fn, label="t", attempts=0) == "ok"
        assert calls["n"] == 1


class TestRetryCallObservability:
    async def test_each_retry_reports_metrics_and_progress(self, captured_sleeps, monkeypatch):
        metric_calls: list[tuple] = []
        progress_calls: list[tuple] = []

        monkeypatch.setattr(
            resilience,
            "_log_retry_metrics",
            lambda label, i, attempts, delay, exc: metric_calls.append((label, i, attempts, delay)),
        )

        async def fake_progress(label, i, attempts, exc):
            progress_calls.append((label, i, attempts))

        monkeypatch.setattr(resilience, "_emit_retry_progress", fake_progress)

        fn, _ = _counting(ConnectionError("boom"), ConnectionError("boom"), "ok")
        await resilience.retry_call(fn, label="analyst:news", attempts=3, base_delay=1.0)

        # The reported delay is the jittered value actually slept, bounded by
        # the doubling ceiling for that attempt.
        assert [(label, i, n) for label, i, n, _ in metric_calls] == [
            ("analyst:news", 0, 3),
            ("analyst:news", 1, 3),
        ]
        for (_, _, _, delay), ceiling in zip(metric_calls, [1.0, 2.0], strict=True):
            assert 0.0 <= delay <= ceiling
        assert progress_calls == [("analyst:news", 0, 3), ("analyst:news", 1, 3)]

    async def test_no_reporting_when_the_call_succeeds(self, captured_sleeps, monkeypatch):
        metric_calls: list = []
        monkeypatch.setattr(
            resilience, "_log_retry_metrics", lambda *a: metric_calls.append(a)
        )
        await resilience.retry_call(lambda: "ok", label="t", attempts=3)
        assert metric_calls == []
