from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import weakref
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_logger = logging.getLogger(__name__)

# LangGraph owns its checkpoint schema. setup() is idempotent/version-aware and
# runs once per DSN per process. Application tables remain Alembic-owned.
#
# A DSN is only recorded here *after* setup() has returned, and every caller
# serialises on the same per-DSN lock while that runs. Marking readiness up
# front (the previous behaviour) let a second caller skip setup and query
# ``checkpoints`` while the first one was still creating it, which surfaced as
# ``relation "checkpoints" does not exist``. It also made a failed setup
# permanent for the life of the process, because the DSN stayed marked ready.
_pg_ready: set[str] = set()
_pg_state_lock = threading.Lock()
_pg_setup_locks: dict[str, threading.Lock] = {}
# asyncio.Lock binds to the loop that first awaits it, so the async locks are
# kept per running loop. The weak keys let a finished loop's locks be collected.
_pg_async_setup_locks: weakref.WeakKeyDictionary[Any, dict[str, asyncio.Lock]] = weakref.WeakKeyDictionary()
_RETIRED_CHECKPOINT_NODES = frozenset({"trader", "trader_agent"})


def checkpoint_scope(user_id: int | None, analysis_id: int | str) -> str:
    """Return the stable namespace for one persisted analysis run."""
    if analysis_id is None or str(analysis_id) == "":
        raise ValueError("analysis_id is required for a checkpoint scope")
    owner = "system" if user_id is None else str(user_id)
    return f"user:{owner}:analysis:{analysis_id}"


def thread_id(ticker: str, date: str, scope: str) -> str:
    """Return a LangGraph thread id isolated to one persisted analysis."""
    return hashlib.sha256(f"{scope}:{ticker.upper()}:{date}".encode()).hexdigest()[:24]


def postgres_dsn() -> str:
    """Return the psycopg DSN; PostgreSQL is mandatory for checkpoints."""
    from backend.core.config import get_settings

    url = (get_settings().DATABASE_URL or "").strip()
    scheme, sep, rest = url.partition("://")
    if not sep or not scheme.lower().startswith("postgres"):
        raise RuntimeError(
            "LangGraph checkpoints require PostgreSQL. The SQLite checkpoint fallback has been removed."
        )
    return f"postgresql://{rest}"


def _schema_is_ready(dsn: str) -> bool:
    with _pg_state_lock:
        return dsn in _pg_ready


def _mark_schema_ready(dsn: str) -> None:
    with _pg_state_lock:
        _pg_ready.add(dsn)


def _setup_lock(dsn: str) -> threading.Lock:
    with _pg_state_lock:
        return _pg_setup_locks.setdefault(dsn, threading.Lock())


def _async_setup_lock(dsn: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    with _pg_state_lock:
        return _pg_async_setup_locks.setdefault(loop, {}).setdefault(dsn, asyncio.Lock())


def reset_schema_readiness() -> None:
    """Forget which DSNs have been set up (used by tests and after a DB reset)."""
    with _pg_state_lock:
        _pg_ready.clear()
        _pg_setup_locks.clear()
        _pg_async_setup_locks.clear()


_INSUFFICIENT_PRIVILEGE = "42501"
_UNDEFINED_TABLE = "42P01"

PROVISIONING_REQUIRED = (
    "The database role this application connects with is not allowed to create "
    "LangGraph's checkpoint tables, and they do not exist yet. A hardened "
    "deployment gives the runtime role no CREATE on its schema by design, so "
    "the tables have to be provisioned once with the migration credential:\n"
    "    python backend/scripts/provision-checkpoints.py\n"
    "The Linux installer and updater run this automatically after Alembic."
)


def _sqlstate_matches(exc: BaseException, sqlstate: str) -> bool:
    """Whether ``exc`` (or what it wraps) carries this PostgreSQL error code."""
    for error in (exc, exc.__cause__, exc.__context__):
        if error is None:
            continue
        if getattr(error, "sqlstate", None) == sqlstate:
            return True
    return False


def checkpoint_tables_exist(dsn: str) -> bool:
    """Whether LangGraph's checkpoint tables are already present.

    Asked on a short-lived connection of its own rather than through the
    saver, so it cannot be confused by the state of a connection whose last
    statement just failed.
    """
    import psycopg

    with psycopg.connect(dsn) as conn:
        row = conn.execute("SELECT to_regclass('public.checkpoints')").fetchone()
        return bool(row and row[0])


async def checkpoint_tables_exist_async(dsn: str) -> bool:
    """Async twin of :func:`checkpoint_tables_exist`."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        cursor = await conn.execute("SELECT to_regclass('public.checkpoints')")
        row = await cursor.fetchone()
        return bool(row and row[0])


def _is_privilege_error(exc: BaseException) -> bool:
    """Whether setup() failed because this role may not create the schema.

    ``setup()`` is how LangGraph owns its own tables, but it needs CREATE. In a
    deployment where the runtime role is deliberately a non-owner, that call
    fails even when the tables are already there and perfectly usable — so a
    permission error is only fatal when the tables are genuinely missing. Every
    other failure is a real one and propagates untouched.
    """
    return _sqlstate_matches(exc, _INSUFFICIENT_PRIVILEGE)


def _ensure_pg_schema(dsn: str, saver: Any) -> None:
    """Create LangGraph's checkpoint tables once per DSN, blocking other callers."""
    if _schema_is_ready(dsn):
        return
    with _setup_lock(dsn):
        if _schema_is_ready(dsn):
            return
        try:
            saver.setup()
        except Exception as exc:
            # The probe costs a connection, so it is only worth making once the
            # error is known to be about privileges.
            if not _is_privilege_error(exc):
                raise
            if not checkpoint_tables_exist(dsn):
                raise RuntimeError(PROVISIONING_REQUIRED) from exc
            _logger.debug("Checkpoint tables already provisioned; this role cannot run setup().")
        _mark_schema_ready(dsn)


async def _ensure_pg_schema_async(dsn: str, saver: Any) -> None:
    """Async twin of :func:`_ensure_pg_schema`.

    A blocking lock cannot be held across ``await`` here: a second coroutine on
    the same loop would stall the loop waiting for it, and the coroutine that
    holds it could never resume.
    """
    if _schema_is_ready(dsn):
        return
    async with _async_setup_lock(dsn):
        if _schema_is_ready(dsn):
            return
        try:
            await saver.setup()
        except Exception as exc:
            if not _is_privilege_error(exc):
                raise
            if not await checkpoint_tables_exist_async(dsn):
                raise RuntimeError(PROVISIONING_REQUIRED) from exc
            _logger.debug("Checkpoint tables already provisioned; this role cannot run setup().")
        _mark_schema_ready(dsn)


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str, scope: str) -> Generator[Any, None, None]:
    del data_dir, ticker, scope
    dsn = postgres_dsn()
    with PostgresSaver.from_conn_string(dsn) as saver:
        _ensure_pg_schema(dsn, saver)
        yield saver


@asynccontextmanager
async def get_async_checkpointer(
    data_dir: str | Path,
    ticker: str,
    scope: str,
) -> AsyncGenerator[Any, None]:
    del data_dir, ticker, scope
    dsn = postgres_dsn()
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await _ensure_pg_schema_async(dsn, saver)
        yield saver


def is_missing_checkpoint_relation(exc: BaseException) -> bool:
    """Whether ``exc`` is PostgreSQL complaining about an absent checkpoint table.

    The tables can vanish under a process that already recorded the DSN as set
    up — a dropped/recreated database, a restored dump, a switched schema. The
    readiness cache is then a lie, so callers reset it and let setup run again
    instead of failing every checkpoint read for the rest of the process.
    """
    return _sqlstate_matches(exc, _UNDEFINED_TABLE)


def checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    tid = thread_id(ticker, date, scope)
    for attempt in (1, 2):
        try:
            with get_checkpointer(data_dir, ticker, scope) as saver:
                cp = saver.get_tuple({"configurable": {"thread_id": tid}})
                if cp is None:
                    return None
                return cp.metadata.get("step")
        except Exception as exc:
            if attempt == 2 or not is_missing_checkpoint_relation(exc):
                raise
            _logger.warning("Checkpoint tables are missing; re-running LangGraph setup.")
            reset_schema_readiness()
    return None


async def async_checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    tid = thread_id(ticker, date, scope)
    for attempt in (1, 2):
        try:
            async with get_async_checkpointer(data_dir, ticker, scope) as saver:
                cp = await saver.aget_tuple({"configurable": {"thread_id": tid}})
                if cp is None:
                    return None
                return cp.metadata.get("step")
        except Exception as exc:
            if attempt == 2 or not is_missing_checkpoint_relation(exc):
                raise
            _logger.warning("Checkpoint tables are missing; re-running LangGraph setup.")
            reset_schema_readiness()
    return None


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str, scope: str) -> None:
    tid = thread_id(ticker, date, scope)
    try:
        with get_checkpointer(data_dir, ticker, scope) as saver:
            saver.delete_thread(tid)
    except Exception as exc:
        _logger.debug("clear_checkpoint skipped for %s/%s: %s", ticker, date, exc)


def _advanced_node(seen: dict, previous_seen: dict) -> str:
    for node, channels in seen.items():
        if node.startswith("__"):
            continue
        if previous_seen.get(node) != channels:
            return node
    return "START"


def is_retired_checkpoint_node(node_name: str) -> bool:
    """Return whether a checkpoint node was removed from the current graph."""
    normalized = str(node_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in _RETIRED_CHECKPOINT_NODES


def checkpoint_contains_retired_nodes(versions_seen: dict | None) -> bool:
    """Return whether checkpoint history was produced by a retired graph topology."""
    return any(is_retired_checkpoint_node(node) for node in (versions_seen or {}))


async def list_checkpoints_for_thread(
    data_dir: str | Path,
    ticker: str,
    date: str,
    scope: str,
) -> list[dict]:
    """Retrieve resumable checkpoints for a thread from PostgreSQL, ordered by step.

    A checkpoint whose execution history includes a retired graph node belongs
    to an obsolete topology. It may still be inspected as historical database
    data, but it is not a valid resume target for the current graph and is not
    exposed through the Time Travel API.
    """
    from backend.core.catalog import node_progress

    tid = thread_id(ticker, date, scope)
    config = {"configurable": {"thread_id": tid}}

    raw: list[tuple[int, str, dict, str]] = []
    for attempt in (1, 2):
        raw = []
        try:
            async with get_async_checkpointer(data_dir, ticker, scope) as saver:
                async for cp in saver.alist(config):
                    metadata = cp.metadata or {}
                    checkpoint = cp.checkpoint or {}
                    raw.append(
                        (
                            int(metadata.get("step", -1)),
                            cp.config["configurable"]["checkpoint_id"],
                            dict(checkpoint.get("versions_seen") or {}),
                            str(checkpoint.get("ts") or metadata.get("ts") or ""),
                        )
                    )
            break
        except Exception as exc:
            if attempt == 2 or not is_missing_checkpoint_relation(exc):
                raise
            _logger.warning("Checkpoint tables are missing; re-running LangGraph setup.")
            reset_schema_readiness()

    raw.sort(key=lambda item: item[0])
    checkpoints = []
    previous_seen: dict = {}
    for step, checkpoint_id, seen, ts in raw:
        node_name = _advanced_node(seen, previous_seen)
        previous_seen = seen
        if checkpoint_contains_retired_nodes(seen):
            continue
        prog = node_progress(node_name)
        checkpoints.append(
            {
                "checkpoint_id": checkpoint_id,
                "step": step,
                "node": node_name,
                "label": prog.get("label") if prog else node_name,
                "ts": ts,
            }
        )
    return checkpoints
