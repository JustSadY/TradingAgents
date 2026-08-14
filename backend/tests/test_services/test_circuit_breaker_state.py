"""Circuit state is shared between workers and degrades safely without Redis."""

from __future__ import annotations

import pytest

from backend.trading_agents.agents.runtime import circuit_breaker as cb


class _FakeRedis:
    """Minimal hash store covering the commands the breaker uses."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, dict[str, str]] = {}
        self.broken = broken

    def _guard(self) -> None:
        if self.broken:
            raise ConnectionError("redis unavailable")

    async def hgetall(self, key):
        self._guard()
        return dict(self.store.get(key, {}))

    async def hincrby(self, key, field, amount):
        self._guard()
        entry = self.store.setdefault(key, {})
        entry[field] = str(int(entry.get(field, 0)) + amount)
        return int(entry[field])

    async def hset(self, key, field, value):
        self._guard()
        self.store.setdefault(key, {})[field] = str(value)

    async def expire(self, key, seconds):
        self._guard()

    async def delete(self, key):
        self._guard()
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def _clean_local():
    cb.reset_all_local()
    yield
    cb.reset_all_local()


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(cb, "_redis", lambda: client)
    return client


async def test_without_redis_state_stays_in_process(monkeypatch):
    monkeypatch.setattr(cb, "_redis", lambda: None)

    assert await cb.get_state("k") == {"failures": 0, "open_since": None}
    assert (await cb.record_failure("k", threshold=2, cooldown=60))["failures"] == 1

    state = await cb.record_failure("k", threshold=2, cooldown=60)
    assert state["failures"] == 2
    assert state["open_since"] is not None


async def test_circuit_opens_only_at_the_threshold(fake_redis):
    first = await cb.record_failure("k", threshold=3, cooldown=60)
    second = await cb.record_failure("k", threshold=3, cooldown=60)
    third = await cb.record_failure("k", threshold=3, cooldown=60)

    assert first["open_since"] is None
    assert second["open_since"] is None
    assert third["open_since"] is not None


async def test_another_worker_sees_an_open_circuit(fake_redis):
    """The point of the migration: one worker's failures protect the others.

    Clearing the local store stands in for a second process, which has its own
    memory but shares the Redis view.
    """
    for _ in range(3):
        await cb.record_failure("k", threshold=3, cooldown=60)

    cb.reset_all_local()
    state = await cb.get_state("k")

    assert state["failures"] == 3
    assert state["open_since"] is not None


async def test_reset_closes_the_circuit_everywhere(fake_redis):
    for _ in range(3):
        await cb.record_failure("k", threshold=3, cooldown=60)

    await cb.reset("k")
    cb.reset_all_local()

    assert await cb.get_state("k") == {"failures": 0, "open_since": None}


async def test_a_redis_outage_degrades_instead_of_failing_the_node(monkeypatch):
    """A breaker that cannot reach Redis must not take the analysis down."""
    monkeypatch.setattr(cb, "_redis", lambda: _FakeRedis(broken=True))

    state = await cb.record_failure("k", threshold=2, cooldown=60)
    assert state["failures"] == 1

    # The local fallback keeps counting, so protection is degraded, not absent.
    assert (await cb.get_state("k"))["failures"] == 1
