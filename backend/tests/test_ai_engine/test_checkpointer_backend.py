"""Contract tests for the PostgreSQL-only LangGraph checkpointer."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from backend.core.config import get_settings
from backend.trading_agents.graph import checkpointer as cp


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql://u:p@h/db"),
    ],
)
def test_postgres_dsn_strips_the_sqlalchemy_driver(monkeypatch, database_url, expected):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", database_url, raising=False)
    assert cp.postgres_dsn() == expected


@pytest.mark.parametrize("database_url", ["sqlite+aiosqlite:////tmp/x.db", ""])
def test_postgres_dsn_rejects_non_postgres_backends(monkeypatch, database_url):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", database_url, raising=False)
    with pytest.raises(RuntimeError, match="checkpoints require PostgreSQL"):
        cp.postgres_dsn()


def test_producing_node_comes_from_versions_seen():
    assert cp._advanced_node({}, {}) == "START"
    assert cp._advanced_node({"market_analyst": {"c": 1}}, {}) == "market_analyst"
    assert (
        cp._advanced_node(
            {"market_analyst": {"c": 1}, "news_analyst": {"c": 1}},
            {"market_analyst": {"c": 1}},
        )
        == "news_analyst"
    )


def test_producing_node_ignores_internal_channels():
    assert cp._advanced_node({"__start__": {"c": 1}}, {}) == "START"
    assert (
        cp._advanced_node({"__start__": {"c": 2}, "risk_manager": {"c": 1}}, {"__start__": {"c": 1}})
        == "risk_manager"
    )


async def test_async_checkpointer_rejects_sqlite_instead_of_restoring_legacy_fallback(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:", raising=False)
    scope = cp.checkpoint_scope(user_id=11, analysis_id=77)
    with pytest.raises(RuntimeError, match="SQLite checkpoint fallback has been removed"):
        async with cp.get_async_checkpointer(tmp_path, "TSLA", scope):
            pass


class _RecordingSaver:
    """A saver whose setup() is slow enough to expose a mark-before-complete race."""

    def __init__(self, delay: float = 0.0, fail_times: int = 0):
        self.setup_calls = 0
        self.ready = False
        self._delay = delay
        self._fail_times = fail_times

    def setup(self) -> None:
        self.setup_calls += 1
        if self._fail_times >= self.setup_calls:
            raise RuntimeError("setup failed")
        time.sleep(self._delay)
        self.ready = True

    async def asetup(self) -> None:
        self.setup_calls += 1
        if self._fail_times >= self.setup_calls:
            raise RuntimeError("setup failed")
        await asyncio.sleep(self._delay)
        self.ready = True


@pytest.fixture(autouse=True)
def _fresh_schema_readiness():
    cp.reset_schema_readiness()
    yield
    cp.reset_schema_readiness()


def test_concurrent_callers_wait_for_setup_instead_of_querying_missing_tables():
    """The second caller must not proceed while setup() is still running.

    Recording readiness before setup() returned is what produced
    ``relation "checkpoints" does not exist`` on a concurrent reader.
    """
    saver = _RecordingSaver(delay=0.05)
    observed_ready: list[bool] = []

    def worker():
        cp._ensure_pg_schema("postgresql://x/db", saver)
        observed_ready.append(saver.ready)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert saver.setup_calls == 1
    assert observed_ready == [True, True, True, True]


def test_failed_setup_is_retried_rather_than_cached_as_ready():
    saver = _RecordingSaver(fail_times=1)
    with pytest.raises(RuntimeError, match="setup failed"):
        cp._ensure_pg_schema("postgresql://x/db", saver)

    cp._ensure_pg_schema("postgresql://x/db", saver)
    assert saver.setup_calls == 2
    assert saver.ready is True


async def test_async_setup_runs_once_and_blocks_concurrent_callers():
    saver = _RecordingSaver(delay=0.05)
    saver.setup = saver.asetup  # type: ignore[method-assign]
    dsn = "postgresql://x/db"

    async def worker() -> bool:
        await cp._ensure_pg_schema_async(dsn, saver)
        return saver.ready

    results = await asyncio.gather(*(worker() for _ in range(4)))
    assert saver.setup_calls == 1
    assert results == [True, True, True, True]


def test_missing_relation_is_recognised_through_the_exception_chain():
    class Undefined(Exception):
        sqlstate = "42P01"

    wrapped = RuntimeError("query failed")
    wrapped.__cause__ = Undefined()

    assert cp.is_missing_checkpoint_relation(Undefined()) is True
    assert cp.is_missing_checkpoint_relation(wrapped) is True
    assert cp.is_missing_checkpoint_relation(RuntimeError("unrelated")) is False


class _Sqlstate(Exception):
    """Stands in for a psycopg error, which carries the code as `sqlstate`."""

    def __init__(self, sqlstate: str, message: str = "boom"):
        super().__init__(message)
        self.sqlstate = sqlstate


class TestPrivilegeHandling:
    """A hardened deployment's runtime role cannot run LangGraph's setup().

    It is a non-owner with no CREATE on its schema by design, so setup() raises
    insufficient_privilege. That is only a real failure when the tables are
    genuinely absent; when they are already provisioned the app must carry on.
    """

    def test_setup_is_tolerated_when_the_tables_already_exist(self, monkeypatch):
        saver = _RecordingSaver()
        saver.setup = lambda: (_ for _ in ()).throw(_Sqlstate("42501"))
        monkeypatch.setattr(cp, "checkpoint_tables_exist", lambda dsn: True)

        cp._ensure_pg_schema("postgresql://x/db", saver)

        assert cp._schema_is_ready("postgresql://x/db") is True

    def test_a_missing_schema_reports_how_to_provision_it(self, monkeypatch):
        saver = _RecordingSaver()
        saver.setup = lambda: (_ for _ in ()).throw(_Sqlstate("42501"))
        monkeypatch.setattr(cp, "checkpoint_tables_exist", lambda dsn: False)

        with pytest.raises(RuntimeError, match="provision-checkpoints.py"):
            cp._ensure_pg_schema("postgresql://x/db", saver)

        # A failure must not be cached as ready, or the next call would query
        # tables that do not exist and report a missing relation instead.
        assert cp._schema_is_ready("postgresql://x/db") is False

    def test_an_unrelated_setup_failure_still_propagates(self, monkeypatch):
        saver = _RecordingSaver()
        saver.setup = lambda: (_ for _ in ()).throw(_Sqlstate("08006", "connection failure"))
        monkeypatch.setattr(cp, "checkpoint_tables_exist", lambda dsn: True)

        with pytest.raises(_Sqlstate):
            cp._ensure_pg_schema("postgresql://x/db", saver)

    async def test_the_async_path_applies_the_same_rule(self, monkeypatch):
        saver = _RecordingSaver()

        async def denied():
            raise _Sqlstate("42501")

        saver.setup = denied

        async def tables_exist(dsn):
            return True

        monkeypatch.setattr(cp, "checkpoint_tables_exist_async", tables_exist)
        await cp._ensure_pg_schema_async("postgresql://x/db", saver)
        assert cp._schema_is_ready("postgresql://x/db") is True

    async def test_the_async_path_also_refuses_a_missing_schema(self, monkeypatch):
        saver = _RecordingSaver()

        async def denied():
            raise _Sqlstate("42501")

        saver.setup = denied

        async def tables_absent(dsn):
            return False

        monkeypatch.setattr(cp, "checkpoint_tables_exist_async", tables_absent)
        with pytest.raises(RuntimeError, match="provision-checkpoints.py"):
            await cp._ensure_pg_schema_async("postgresql://x/db", saver)

    def test_the_message_names_the_cause_and_the_remedy(self):
        message = cp.PROVISIONING_REQUIRED
        assert "not allowed to create" in message
        assert "provision-checkpoints.py" in message

    @pytest.mark.parametrize(
        ("sqlstate", "expected"),
        [("42P01", True), ("42501", False), (None, False)],
    )
    def test_missing_relation_detection_is_code_based(self, sqlstate, expected):
        exc = _Sqlstate(sqlstate) if sqlstate else RuntimeError("plain")
        assert cp.is_missing_checkpoint_relation(exc) is expected
