"""PostgreSQL pgvector-backed :class:`MemoryStore`.

Self-hosted alternative to Pinecone: episodes live in a ``memory_vectors``
table inside the app's own PostgreSQL database. Embedding is always
client-side (an :class:`Embedder` is required — there is no hosted inference).

The table uses a dimension-less ``vector`` column with exact cosine scans:
per-user episodic memory stays in the hundreds-to-thousands of rows, where a
sequential scan beats maintaining an ANN index. Rows whose stored dimension
differs from the active embed model are skipped via ``vector_dims`` so
switching models never errors. Schema setup is lazy and idempotent; the
``vector`` extension must be installable (``CREATE EXTENSION vector``).

Queries never raise — a missing extension or transient error yields an empty
result, matching the ``MemoryStore`` contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .base import Embedder, MemoryHit, MemoryRecord

_logger = logging.getLogger(__name__)

_SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE TABLE IF NOT EXISTS memory_vectors ("
    " namespace TEXT NOT NULL,"
    " id TEXT NOT NULL,"
    " text TEXT NOT NULL DEFAULT '',"
    " metadata JSONB NOT NULL DEFAULT '{}'::jsonb,"
    " embedding vector NOT NULL,"
    " PRIMARY KEY (namespace, id)"
    ")",
)

def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(v)) for v in values) + "]"

class PgVectorMemoryStore:
    def __init__(self, embedder: Embedder, *, engine=None):
        self._embedder = embedder
        self._engine = engine
        self._ready = False
        self._schema_lock = asyncio.Lock()

    def _get_engine(self):
        if self._engine is None:
            from backend.core.database import engine

            self._engine = engine
        return self._engine

    async def _ensure_schema(self) -> bool:
        if self._ready:
            return True
        async with self._schema_lock:
            if self._ready:
                return True
            from sqlalchemy import text as sql_text

            engine = self._get_engine()
            if engine.dialect.name != "postgresql":
                _logger.warning(
                    "pgvector memory requires PostgreSQL (got dialect %s); memory disabled", engine.dialect.name
                )
                return False
            try:
                async with engine.begin() as conn:
                    for stmt in _SCHEMA_STATEMENTS:
                        await conn.execute(sql_text(stmt))
                self._ready = True
            except Exception as exc:  # noqa: BLE001 — memory init must never break a run
                _logger.warning("pgvector schema setup failed (is the extension available?): %s", exc)
                return False
        return True

    async def upsert(self, namespace: str, records: list[MemoryRecord]) -> None:
        if not records:
            return
        if not await self._ensure_schema():
            raise RuntimeError("pgvector memory store unavailable")
        from sqlalchemy import text as sql_text

        vectors = await self._embedder.embed([r.text for r in records])
        stmt = sql_text(
            "INSERT INTO memory_vectors (namespace, id, text, metadata, embedding) "
            "VALUES (:namespace, :id, :text, CAST(:metadata AS jsonb), CAST(:embedding AS vector)) "
            "ON CONFLICT (namespace, id) DO UPDATE SET"
            " text = EXCLUDED.text, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding"
        )
        params = [
            {
                "namespace": namespace,
                "id": record.id,
                "text": record.text,
                "metadata": json.dumps(record.metadata or {}, default=str),
                "embedding": _vector_literal(vector),
            }
            for record, vector in zip(records, vectors, strict=True)
        ]
        async with self._get_engine().begin() as conn:
            await conn.execute(stmt, params)

    async def query(
        self,
        namespace: str,
        text: str,
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryHit]:
        try:
            if not await self._ensure_schema():
                return []
            from sqlalchemy import text as sql_text

            vector = (await self._embedder.embed([text]))[0]
            sql = (
                "SELECT id, text, metadata, 1 - (embedding <=> CAST(:vec AS vector)) AS score "
                "FROM memory_vectors "
                "WHERE namespace = :namespace AND vector_dims(embedding) = :dim "
            )
            params: dict[str, Any] = {
                "vec": _vector_literal(vector),
                "namespace": namespace,
                "dim": len(vector),
                "top_k": int(top_k),
            }
            if metadata_filter:
                sql += "AND metadata @> CAST(:filter AS jsonb) "
                params["filter"] = json.dumps(metadata_filter, default=str)
            sql += "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :top_k"

            async with self._get_engine().connect() as conn:
                rows = (await conn.execute(sql_text(sql), params)).fetchall()

            hits: list[MemoryHit] = []
            for row in rows:
                metadata = row.metadata
                if isinstance(metadata, str):
                    metadata = json.loads(metadata or "{}")
                hits.append(
                    MemoryHit(
                        id=row.id,
                        score=float(row.score or 0.0),
                        text=row.text or "",
                        metadata=dict(metadata or {}),
                    )
                )
            return hits
        except Exception as exc:  # noqa: BLE001 — memory is best-effort; never break a run
            _logger.warning("pgvector query failed (namespace=%s): %s", namespace, exc)
            return []
