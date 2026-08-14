"""Backend selection and checkpoint listing for the LangGraph saver."""

from __future__ import annotations

import pytest

from backend.core.config import get_settings
from backend.trading_agents.graph import checkpointer as cp


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgresql+asyncpg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql://u:p@h/db"),
        ("sqlite+aiosqlite:////tmp/x.db", None),
        ("", None),
    ],
)
def test_postgres_dsn_strips_the_sqlalchemy_driver(monkeypatch, database_url, expected):
    """Checkpoints follow the application database.

    psycopg cannot parse the ``postgresql+asyncpg`` form SQLAlchemy needs, and a
    non-PostgreSQL URL has to fall back to the per-analysis SQLite files.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", database_url, raising=False)
    assert cp.postgres_dsn() == expected


def test_producing_node_comes_from_versions_seen():
    """``metadata["writes"]`` is gone, so the node is diffed out of the state.

    LangGraph's CheckpointMetadata no longer carries ``writes`` and the Pregel
    loop never sets it, so the previous lookup reported "START" for every
    checkpoint. ``versions_seen`` round-trips on both savers.
    """
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
    """LangGraph's ``__`` bookkeeping entries are not analyst nodes."""
    assert cp._advanced_node({"__start__": {"c": 1}}, {}) == "START"
    assert (
        cp._advanced_node({"__start__": {"c": 2}, "risk_manager": {"c": 1}}, {"__start__": {"c": 1}})
        == "risk_manager"
    )


async def test_checkpoint_listing_round_trip_on_sqlite(tmp_path, monkeypatch):
    """The SQLite fallback lists checkpoints in step order with node labels."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///:memory:", raising=False)

    scope = cp.checkpoint_scope(user_id=11, analysis_id=77)
    tid = cp.thread_id("TSLA", "2026-08-14", scope)

    async with cp.get_async_checkpointer(tmp_path, "TSLA", scope) as saver:
        config = {"configurable": {"thread_id": tid, "checkpoint_ns": ""}}
        for step, seen in [
            (0, {}),
            (1, {"market_analyst": {"c": 1}}),
            (2, {"market_analyst": {"c": 1}, "news_analyst": {"c": 1}}),
        ]:
            await saver.aput(
                config,
                {
                    "v": 1,
                    "id": f"cp-{step}",
                    "ts": f"2026-08-14T00:0{step}:00+00:00",
                    "channel_values": {},
                    "channel_versions": {},
                    "versions_seen": seen,
                    "pending_sends": [],
                },
                {"step": step, "source": "loop"},
                {},
            )

    rows = await cp.list_checkpoints_for_thread(tmp_path, "TSLA", "2026-08-14", scope)
    assert [(r["step"], r["node"]) for r in rows] == [
        (0, "START"),
        (1, "market_analyst"),
        (2, "news_analyst"),
    ]

    cp.clear_checkpoint(tmp_path, "TSLA", "2026-08-14", scope)
    assert await cp.list_checkpoints_for_thread(tmp_path, "TSLA", "2026-08-14", scope) == []
