from __future__ import annotations

import asyncio
import time

import backend.services.memory_service as memory_service
from backend.services.memory_service import (
    _collection_name,
    _get_or_build_mem0,
    _mem0_connection_string,
    recall_episode_lessons,
    record_episode,
)


class _Memory:
    def __init__(self, hits=None):
        self.adds = []
        self.deletes = []
        self.searches = []
        self.hits = list(hits or [])

    def delete_all(self, **kwargs):
        self.deletes.append(kwargs)
        return {"message": "deleted"}

    def add(self, messages, **kwargs):
        self.adds.append((messages, kwargs))
        return {"results": [{"event": "ADD"}]}

    def search(self, query, **kwargs):
        self.searches.append((query, kwargs))
        return {"results": self.hits[: kwargs.get("top_k", 5)]}


def _episode_hit(reflection: str = "Momentum confirmation mattered.") -> dict:
    return {
        "id": "episode",
        "score": 0.91,
        "metadata": {
            "ticker": "AAPL",
            "trade_date": "2026-08-10",
            "signal": "Buy",
            "alpha_return": 0.04,
            "outcome": "gain",
            "reflection": reflection,
            "outcome_available_at": "2026-08-20T18:00:00+00:00",
        },
    }


def test_mem0_connection_string_uses_psycopg_compatible_postgres_url() -> None:
    assert (
        _mem0_connection_string("postgresql+asyncpg://user:secret@db:5432/tradingagents")
        == "postgresql://user:secret@db:5432/tradingagents"
    )
    assert _mem0_connection_string("sqlite+aiosqlite:///test.db") is None


def test_mem0_collection_separates_embedding_vector_spaces() -> None:
    openai_small = _collection_name("openai", "text-embedding-3-small", 1536)
    openai_large = _collection_name("openai", "text-embedding-3-large", 3072)
    ollama = _collection_name("ollama", "nomic-embed-text", 768)

    assert openai_small != openai_large
    assert openai_small != ollama
    assert openai_small.startswith("tradingagents_mem0_openai_")


async def test_mem0_initialization_is_single_flight_per_effective_config(monkeypatch) -> None:
    cache_key = ("test-db", "openai", "test-model", 1536, "", "test-key")
    memory_service._store_cache.pop(cache_key, None)
    memory_service._store_init_tasks.pop(cache_key, None)
    build_calls = 0
    built_store = object()

    def fake_build_mem0(**_kwargs):
        nonlocal build_calls
        build_calls += 1
        time.sleep(0.05)
        return built_store

    monkeypatch.setattr(memory_service, "_build_mem0", fake_build_mem0)

    try:
        first, second, third = await asyncio.gather(
            _get_or_build_mem0(
                cache_key,
                database_url="postgresql+asyncpg://test",
                embedder_kind="openai",
                embed_model="test-model",
                openai_api_key="secret",
                ollama_base_url="http://localhost:11434",
            ),
            _get_or_build_mem0(
                cache_key,
                database_url="postgresql+asyncpg://test",
                embedder_kind="openai",
                embed_model="test-model",
                openai_api_key="secret",
                ollama_base_url="http://localhost:11434",
            ),
            _get_or_build_mem0(
                cache_key,
                database_url="postgresql+asyncpg://test",
                embedder_kind="openai",
                embed_model="test-model",
                openai_api_key="secret",
                ollama_base_url="http://localhost:11434",
            ),
        )

        assert first is built_store
        assert second is built_store
        assert third is built_store
        assert build_calls == 1
        assert cache_key not in memory_service._store_init_tasks
    finally:
        memory_service._store_cache.pop(cache_key, None)
        memory_service._store_init_tasks.pop(cache_key, None)


async def test_record_episode_writes_curated_mem0_memory_without_inference() -> None:
    store = _Memory()

    written = await record_episode(
        user_id=9,
        ticker="AAPL",
        trade_date="2026-08-10",
        signal="Buy",
        situation_text="Strong earnings with improving margins.",
        decision="Buy with controlled sizing.",
        raw_return=0.08,
        alpha_return=0.04,
        reflection="Momentum confirmation mattered.",
        store=store,
    )

    assert written is True
    assert store.deletes == [
        {
            "user_id": "9",
            "agent_id": "trading-episodes",
            "run_id": "9:AAPL:2026-08-10",
        }
    ]
    assert len(store.adds) == 1
    messages, kwargs = store.adds[0]
    assert "Momentum confirmation mattered" in messages
    assert kwargs["user_id"] == "9"
    assert kwargs["agent_id"] == "trading-episodes"
    assert kwargs["run_id"] == "9:AAPL:2026-08-10"
    assert kwargs["infer"] is False
    assert kwargs["metadata"]["memory_type"] == "trading_episode"
    assert kwargs["metadata"]["outcome"] == "gain"


async def test_identical_episode_recall_reuses_short_lived_vector_search() -> None:
    store = _Memory([_episode_hit()])

    first = await recall_episode_lessons(
        user_id=9,
        situation_text="strong earnings and improving margins",
        top_k=5,
        store=store,
    )
    second = await recall_episode_lessons(
        user_id=9,
        situation_text="strong earnings and improving margins",
        top_k=5,
        store=store,
    )

    assert first == second
    assert "Momentum confirmation mattered" in first
    assert len(store.searches) == 1


async def test_episode_write_invalidates_cached_recall() -> None:
    store = _Memory([_episode_hit("Old lesson")])
    query = "strong earnings and improving margins"

    first = await recall_episode_lessons(user_id=9, situation_text=query, top_k=5, store=store)
    assert "Old lesson" in first
    assert len(store.searches) == 1

    store.hits = [_episode_hit("New lesson")]
    assert await record_episode(
        user_id=9,
        ticker="AAPL",
        trade_date="2026-08-10",
        signal="Buy",
        situation_text="Strong earnings with improving margins.",
        decision="Buy with controlled sizing.",
        raw_return=0.08,
        alpha_return=0.04,
        reflection="New lesson",
        store=store,
    )

    second = await recall_episode_lessons(user_id=9, situation_text=query, top_k=5, store=store)
    assert "New lesson" in second
    assert len(store.searches) == 2


async def test_episode_recall_keeps_historical_outcome_causality() -> None:
    store = _Memory(
        [
            {
                "id": "old-loss",
                "score": 0.88,
                "metadata": {
                    "ticker": "NVDA",
                    "trade_date": "2026-07-01",
                    "signal": "Buy",
                    "alpha_return": -0.05,
                    "outcome": "loss",
                    "reflection": "Do not chase the gap without confirmation.",
                    "outcome_available_at": "2026-07-15T18:00:00+00:00",
                },
            },
            {
                "id": "future-gain",
                "score": 0.99,
                "metadata": {
                    "ticker": "NVDA",
                    "trade_date": "2026-09-01",
                    "signal": "Buy",
                    "alpha_return": 0.12,
                    "outcome": "gain",
                    "reflection": "Future lesson must not leak.",
                    "outcome_available_at": "2026-09-20T18:00:00+00:00",
                },
            },
        ]
    )

    recalled = await recall_episode_lessons(
        user_id=9,
        situation_text="high momentum after a gap",
        top_k=2,
        as_of="2026-08-01",
        store=store,
    )

    assert "Do not chase the gap without confirmation" in recalled
    assert "Future lesson must not leak" not in recalled
    assert "do NOT repeat the same mistake" in recalled
    query, kwargs = store.searches[0]
    assert query == "high momentum after a gap"
    assert kwargs["filters"] == {"user_id": "9", "agent_id": "trading-episodes"}
    assert kwargs["top_k"] == 10
