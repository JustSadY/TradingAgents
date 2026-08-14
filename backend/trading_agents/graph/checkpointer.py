from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.core.utils import safe_ticker_component

_logger = logging.getLogger(__name__)

# LangGraph owns the checkpoint schema and its setup() is idempotent and
# version-aware, so it runs once per DSN per process rather than being folded
# into Alembic. Alembic still owns every application table.
_pg_ready: set[str] = set()
_pg_ready_lock = threading.Lock()

def checkpoint_scope(user_id: int | None, analysis_id: int | str) -> str:
    """Return the stable namespace for one persisted analysis run.

    Checkpoints contain the complete LangGraph state, including reports and
    tool outputs.  A ticker/date is therefore not a sufficient identity: two
    users (or two independent runs by the same user) can legitimately analyse
    the same asset on the same day.  Keep the owner and persisted analysis row
    in every checkpoint identity so those runs can never resume each other.
    """
    if analysis_id is None or str(analysis_id) == "":
        raise ValueError("analysis_id is required for a checkpoint scope")
    owner = "system" if user_id is None else str(user_id)
    return f"user:{owner}:analysis:{analysis_id}"

def _scope_component(scope: str) -> str:
    if not isinstance(scope, str) or not scope:
        raise ValueError("checkpoint scope is required")
    return hashlib.sha256(scope.encode()).hexdigest()[:24]

def _db_path(data_dir: str | Path, ticker: str, scope: str) -> Path:
    """Filesystem location of the SQLite fallback database.

    Only used when the application database is not PostgreSQL; see
    :func:`postgres_dsn`.
    """
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints" / _scope_component(scope)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"

def thread_id(ticker: str, date: str, scope: str) -> str:
    """Return a LangGraph thread id isolated to one persisted analysis."""
    return hashlib.sha256(f"{scope}:{ticker.upper()}:{date}".encode()).hexdigest()[:24]

def postgres_dsn() -> str | None:
    """Return a psycopg DSN when the app database is PostgreSQL, else ``None``.

    Checkpoints belong in the same database as the rest of the application so
    an analysis can resume on any worker or pod, and so backups cover the two
    together. ``DATABASE_URL`` is normalised to the ``postgresql+asyncpg``
    SQLAlchemy form; psycopg — which the LangGraph saver uses — wants the plain
    scheme, so strip the driver suffix.

    Returning ``None`` selects the per-analysis SQLite files, which is what the
    test suite and any SQLite deployment get.
    """
    from backend.core.config import get_settings

    url = (get_settings().DATABASE_URL or "").strip()
    scheme, sep, rest = url.partition("://")
    if not sep or not scheme.lower().startswith("postgres"):
        return None
    return f"postgresql://{rest}"

def _ensure_pg_schema(dsn: str) -> bool:
    """Return True when this process still needs to run ``setup()`` for *dsn*."""
    with _pg_ready_lock:
        if dsn in _pg_ready:
            return False
        _pg_ready.add(dsn)
        return True

@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str, scope: str) -> Generator[Any, None, None]:
    dsn = postgres_dsn()
    if dsn is None:
        db = _db_path(data_dir, ticker, scope)
        conn = sqlite3.connect(str(db), check_same_thread=False)
        try:
            saver = SqliteSaver(conn)
            saver.setup()
            yield saver
        finally:
            conn.close()
        return

    with PostgresSaver.from_conn_string(dsn) as saver:
        if _ensure_pg_schema(dsn):
            saver.setup()
        yield saver

@asynccontextmanager
async def get_async_checkpointer(data_dir: str | Path, ticker: str, scope: str) -> AsyncGenerator[Any, None]:
    dsn = postgres_dsn()
    if dsn is None:
        db = _db_path(data_dir, ticker, scope)
        async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
            await saver.setup()
            yield saver
        return

    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        if _ensure_pg_schema(dsn):
            await saver.setup()
        yield saver

def checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    tid = thread_id(ticker, date, scope)
    with get_checkpointer(data_dir, ticker, scope) as saver:
        cp = saver.get_tuple({"configurable": {"thread_id": tid}})
        if cp is None:
            return None
        return cp.metadata.get("step")

async def async_checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    tid = thread_id(ticker, date, scope)
    async with get_async_checkpointer(data_dir, ticker, scope) as saver:
        cp = await saver.aget_tuple({"configurable": {"thread_id": tid}})
        if cp is None:
            return None
        return cp.metadata.get("step")

def clear_checkpoint(data_dir: str | Path, ticker: str, date: str, scope: str) -> None:
    """Drop every checkpoint for one analysis thread.

    Uses the saver's own ``delete_thread`` rather than hand-written DELETEs, so
    the PostgreSQL and SQLite backends stay consistent and neither can miss a
    table LangGraph adds later.
    """
    tid = thread_id(ticker, date, scope)
    try:
        with get_checkpointer(data_dir, ticker, scope) as saver:
            saver.delete_thread(tid)
    except Exception as exc:
        _logger.debug("clear_checkpoint skipped for %s/%s: %s", ticker, date, exc)

def _advanced_node(seen: dict, previous_seen: dict) -> str:
    """Name the node that produced a checkpoint, by diffing ``versions_seen``.

    LangGraph used to record the producing node in ``metadata["writes"]``, but
    ``CheckpointMetadata`` no longer carries that key and the Pregel loop never
    sets it, so reading it returned "START" for every checkpoint. The SQLite
    saver stores metadata verbatim and the PostgreSQL one coerces it to the
    typed schema, which is why the dead field was easy to miss.

    ``versions_seen`` maps node -> channel -> version and survives both
    backends. The node whose entry changed since the previous checkpoint is the
    one that just ran.
    """
    for node, channels in seen.items():
        if node.startswith("__"):
            continue
        if previous_seen.get(node) != channels:
            return node
    return "START"

async def list_checkpoints_for_thread(data_dir: str | Path, ticker: str, date: str, scope: str) -> list[dict]:
    """Retrieve all checkpoints for a thread from the saver, ordered by step."""
    from backend.core.catalog import node_progress

    tid = thread_id(ticker, date, scope)
    config = {"configurable": {"thread_id": tid}}

    raw: list[tuple[int, str, dict, str]] = []
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

    raw.sort(key=lambda item: item[0])

    checkpoints = []
    previous_seen: dict = {}
    for step, checkpoint_id, seen, ts in raw:
        node_name = _advanced_node(seen, previous_seen)
        previous_seen = seen
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
