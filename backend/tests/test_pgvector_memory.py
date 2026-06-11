"""Tests for the pgvector memory store.

The degradation tests inject a stub engine so they are deterministic on any
test database. The roundtrip test runs only when the configured database is
PostgreSQL (the CI service image ships the pgvector extension) and uses an
injected deterministic embedder, so no embedding API is needed.
"""

import pytest
from sqlalchemy import text as sql_text

from backend.core.memory import build_pgvector_store
from backend.core.memory.base import MemoryRecord
from backend.core.memory.pgvector_store import PgVectorMemoryStore, _vector_literal


class _FakeDialect:
    name = "sqlite"


class _FakeEngine:
    dialect = _FakeDialect()


class _MappedEmbedder:
    """Returns fixed vectors per exact text, so similarity order is known."""

    dimension = 3

    def __init__(self, mapping: dict[str, list[float]]):
        self.mapping = mapping
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return [self.mapping[t] for t in texts]


def test_vector_literal_format():
    assert _vector_literal([0.1, -2.0, 3]) == "[0.1,-2.0,3.0]"


def test_factory_requires_openai_key():
    assert build_pgvector_store(openai_api_key=None) is None
    assert build_pgvector_store(openai_api_key="") is None


def test_factory_builds_store_with_key():
    store = build_pgvector_store(openai_api_key="sk-test")
    assert isinstance(store, PgVectorMemoryStore)


async def test_query_degrades_to_empty_on_non_postgres():
    embedder = _MappedEmbedder({})
    store = PgVectorMemoryStore(embedder, engine=_FakeEngine())
    assert await store.query("ep_user_1", "breakout momentum") == []
    assert embedder.calls == 0


async def test_upsert_raises_on_non_postgres():
    store = PgVectorMemoryStore(_MappedEmbedder({}), engine=_FakeEngine())
    with pytest.raises(RuntimeError):
        await store.upsert("ep_user_1", [MemoryRecord(id="x", text="t")])


async def test_roundtrip_against_postgres():
    from backend.core.database import engine
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        pytest.skip("requires a PostgreSQL test database (pgvector)")

    # Clear any connections in the pool created in previous event loops
    await engine.dispose()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not reachable/running")

    namespace = "test_pgvector_roundtrip"
    embedder = _MappedEmbedder(
        {
            "breakout above resistance": [1.0, 0.0, 0.0],
            "oversold bounce fade": [0.0, 1.0, 0.0],
            "strong breakout momentum": [0.9, 0.1, 0.0],
        }
    )
    store = PgVectorMemoryStore(embedder, engine=engine)
    try:
        await store.upsert(
            namespace,
            [
                MemoryRecord(id="a", text="breakout above resistance", metadata={"outcome": "loss", "alpha": -0.1}),
                MemoryRecord(id="b", text="oversold bounce fade", metadata={"outcome": "gain", "alpha": 0.05}),
            ],
        )

        hits = await store.query(namespace, "strong breakout momentum", top_k=2)
        assert [h.id for h in hits] == ["a", "b"]
        assert hits[0].text == "breakout above resistance"
        assert hits[0].metadata["outcome"] == "loss"
        assert hits[0].score > hits[1].score > 0.0

        filtered = await store.query(namespace, "strong breakout momentum", metadata_filter={"outcome": "gain"})
        assert [h.id for h in filtered] == ["b"]

        assert await store.query("test_pgvector_other_ns", "strong breakout momentum") == []

        # Re-upserting the same id must update in place, not duplicate.
        await store.upsert(
            namespace, [MemoryRecord(id="a", text="breakout above resistance", metadata={"outcome": "gain"})]
        )
        hits = await store.query(namespace, "strong breakout momentum", top_k=5)
        assert len(hits) == 2
        assert hits[0].metadata["outcome"] == "gain"
    finally:
        try:
            async with engine.begin() as conn:
                await conn.execute(sql_text("DELETE FROM memory_vectors WHERE namespace = :ns"), {"ns": namespace})
        except Exception:
            pass
        await engine.dispose()
