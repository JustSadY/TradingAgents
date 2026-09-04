from __future__ import annotations

from backend.services.memory_service import (
    _collection_name,
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
