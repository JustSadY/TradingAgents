"""PostgreSQL pgvector-backed :class:`MemoryStore`.

The ``vector`` extension and ``memory_vectors`` table are owned by Alembic.
Runtime code only verifies that the migration is present; it never performs
schema DDL during an analysis request.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .base import Embedder, MemoryHit, MemoryRecord

_logger = logging.getLogger(__name__)


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
                async with engine.connect() as conn:
                    extension_ready = bool(
                        (
                            await conn.execute(
                                sql_text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                            )
                        ).scalar_one()
                    )
                    table_ready = (
                        await conn.execute(sql_text("SELECT to_regclass('memory_vectors') IS NOT NULL"))
                    ).scalar_one()
                self._ready = bool(extension_ready and table_ready)
                if not self._ready:
                    _logger.warning("pgvector memory schema is missing; run 'alembic upgrade head'")
            except Exception as exc:  # noqa: BLE001 — memory init must never break a run
                _logger.warning("pgvector schema verification failed: %s", exc)
                return False
        return self._ready

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
