"""Contract tests for the PostgreSQL-only LangGraph checkpointer."""

from __future__ import annotations

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
