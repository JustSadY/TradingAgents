from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_logger = logging.getLogger(__name__)

# LangGraph owns its checkpoint schema. setup() is idempotent/version-aware and
# runs once per DSN per process. Application tables remain Alembic-owned.
_pg_ready: set[str] = set()
_pg_ready_lock = threading.Lock()
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


def _ensure_pg_schema(dsn: str) -> bool:
    with _pg_ready_lock:
        if dsn in _pg_ready:
            return False
        _pg_ready.add(dsn)
        return True


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str, scope: str) -> Generator[Any, None, None]:
    del data_dir, ticker, scope
    dsn = postgres_dsn()
    with PostgresSaver.from_conn_string(dsn) as saver:
        if _ensure_pg_schema(dsn):
            saver.setup()
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
    """Return whether a checkpoint belongs to a graph node removed from runtime."""
    normalized = str(node_name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in _RETIRED_CHECKPOINT_NODES


async def list_checkpoints_for_thread(
    data_dir: str | Path,
    ticker: str,
    date: str,
    scope: str,
) -> list[dict]:
    """Retrieve resumable checkpoints for a thread from PostgreSQL, ordered by step.

    Checkpoints produced by retired graph nodes are historical implementation
    artifacts, not valid resume targets for the current graph, so they are not
    exposed through the Time Travel API.
    """
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
        if is_retired_checkpoint_node(node_name):
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
