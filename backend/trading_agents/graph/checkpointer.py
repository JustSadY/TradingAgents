from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.core.utils import safe_ticker_component

_logger = logging.getLogger(__name__)


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
    # Do not put tenant or analysis identifiers directly in a filesystem path.
    return hashlib.sha256(scope.encode()).hexdigest()[:24]


def _db_path(data_dir: str | Path, ticker: str, scope: str) -> Path:
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints" / _scope_component(scope)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str, scope: str) -> str:
    """Return a LangGraph thread id isolated to one persisted analysis."""
    return hashlib.sha256(f"{scope}:{ticker.upper()}:{date}".encode()).hexdigest()[:24]


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str, scope: str) -> Generator[SqliteSaver, None, None]:
    db = _db_path(data_dir, ticker, scope)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


@asynccontextmanager
async def get_async_checkpointer(
    data_dir: str | Path, ticker: str, scope: str
) -> AsyncGenerator[AsyncSqliteSaver, None]:
    db = _db_path(data_dir, ticker, scope)
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        await saver.setup()
        yield saver


def checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    db = _db_path(data_dir, ticker, scope)
    if not db.exists():
        return None
    tid = thread_id(ticker, date, scope)
    with get_checkpointer(data_dir, ticker, scope) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


async def async_checkpoint_step(data_dir: str | Path, ticker: str, date: str, scope: str) -> int | None:
    db = _db_path(data_dir, ticker, scope)
    if not db.exists():
        return None
    tid = thread_id(ticker, date, scope)
    async with get_async_checkpointer(data_dir, ticker, scope) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = await saver.aget_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str, scope: str) -> None:
    db = _db_path(data_dir, ticker, scope)
    if not db.exists():
        return
    tid = thread_id(ticker, date, scope)
    conn = sqlite3.connect(str(db))
    try:
        for table in ("writes", "checkpoints"):
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
        conn.commit()
    except sqlite3.OperationalError as exc:
        # Table may not exist yet (no checkpoint ever written) — non-fatal.
        _logger.debug("clear_checkpoint skipped for %s/%s: %s", ticker, date, exc)
    finally:
        conn.close()


async def list_checkpoints_for_thread(data_dir: str | Path, ticker: str, date: str, scope: str) -> list[dict]:
    """Retrieve all checkpoints for a thread from the saver database, ordered by step."""
    db = _db_path(data_dir, ticker, scope)
    if not db.exists():
        return []

    tid = thread_id(ticker, date, scope)
    config = {"configurable": {"thread_id": tid}}

    checkpoints = []
    async with get_async_checkpointer(data_dir, ticker, scope) as saver:
        async for cp in saver.alist(config):
            metadata = cp.metadata or {}
            step = metadata.get("step", -1)
            writes = metadata.get("writes") or {}
            # Try to identify which node executed to generate this checkpoint
            node_name = next(iter(writes.keys()), "START") if writes else "START"

            # Translate node name into a user-friendly label if possible
            from backend.core.catalog import node_progress

            prog = node_progress(node_name)
            node_label = prog.get("label") if prog else node_name

            checkpoints.append(
                {
                    "checkpoint_id": cp.config["configurable"]["checkpoint_id"],
                    "step": step,
                    "node": node_name,
                    "label": node_label,
                    "ts": metadata.get("ts", ""),
                }
            )

    # Sort checkpoints by step number ascending
    checkpoints.sort(key=lambda x: x["step"])
    return checkpoints
