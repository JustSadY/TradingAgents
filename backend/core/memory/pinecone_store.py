"""Pinecone-backed :class:`MemoryStore`.

Supports two embedding modes:

* **hosted inference** (default, no client embedder): text is sent to Pinecone
  which embeds it server-side with the configured model.
* **client-side vectors** (an :class:`Embedder` is supplied): text is embedded
  locally and upserted as vectors.

The Pinecone SDK is synchronous, so every call is run via ``asyncio.to_thread``
to keep the event loop responsive. Queries never raise — a missing index or
transient error yields an empty result, matching the ``MemoryStore`` contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import Embedder, MemoryHit, MemoryRecord

_logger = logging.getLogger(__name__)

class PineconeMemoryStore:
    def __init__(
        self,
        api_key: str,
        index_name: str,
        *,
        embedder: Embedder | None = None,
        embed_model: str = "llama-text-embed-v2",
        cloud: str = "aws",
        region: str = "us-east-1",
    ):
        from pinecone import Pinecone

        self._pc = Pinecone(api_key=api_key)
        self._index_name = index_name
        self._embedder = embedder
        self._embed_model = embed_model
        self._cloud = cloud
        self._region = region
        self._index = None
        self._index_lock = asyncio.Lock()

    async def _get_index(self):
        if self._index is not None:
            return self._index
        async with self._index_lock:
            if self._index is None:
                self._index = await asyncio.to_thread(self._ensure_index)
        return self._index

    def _ensure_index(self):
        """Create the index if it doesn't exist (idempotent), return a handle."""
        if not self._pc.has_index(self._index_name):
            if self._embedder is None:
                self._pc.create_index_for_model(
                    name=self._index_name,
                    cloud=self._cloud,
                    region=self._region,
                    embed={"model": self._embed_model, "field_map": {"text": "text"}},
                )
            else:
                from pinecone import ServerlessSpec

                self._pc.create_index(
                    name=self._index_name,
                    dimension=self._embedder.dimension,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=self._cloud, region=self._region),
                )
        return self._pc.Index(self._index_name)

    async def upsert(self, namespace: str, records: list[MemoryRecord]) -> None:
        if not records:
            return
        index = await self._get_index()
        if self._embedder is None:
            payload = [{"_id": r.id, "text": r.text, **_clean_metadata(r.metadata)} for r in records]
            await asyncio.to_thread(
                lambda: index.upsert_records(namespace=namespace, records=payload)
            )
        else:
            vectors = await self._embedder.embed([r.text for r in records])
            items = [
                {"id": r.id, "values": vec, "metadata": {**_clean_metadata(r.metadata), "text": r.text}}
                for r, vec in zip(records, vectors, strict=True)
            ]
            await asyncio.to_thread(lambda: index.upsert(vectors=items, namespace=namespace))

    async def query(
        self,
        namespace: str,
        text: str,
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryHit]:
        try:
            index = await self._get_index()
            if self._embedder is None:
                return await asyncio.to_thread(self._search_hosted, index, namespace, text, top_k, metadata_filter)
            vec = (await self._embedder.embed([text]))[0]
            return await asyncio.to_thread(self._query_vectors, index, namespace, vec, top_k, metadata_filter)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort; never break a run
            _logger.warning("Pinecone query failed (namespace=%s): %s", namespace, exc)
            return []

    @staticmethod
    def _hit_field(hit: Any, *names: str) -> Any:
        """First present value among *names* on a hit, dict or model alike.

        The hosted-search wire format names these ``_id``/``_score``, but the
        SDK model renames them (``_id`` is a private attribute in Python) and
        exposes ``id``/``score`` instead. Reading only the wire names raised
        AttributeError, and because memory is best-effort the whole query was
        swallowed into an empty result — agent memory silently retrieved
        nothing.
        """

        for name in names:
            if isinstance(hit, dict):
                if name in hit:
                    return hit[name]
            else:
                value = getattr(hit, name, None)
                if value is not None:
                    return value
        return None

    def _search_hosted(self, index, namespace, text, top_k, metadata_filter) -> list[MemoryHit]:
        query: dict[str, Any] = {"inputs": {"text": text}, "top_k": top_k}
        if metadata_filter:
            query["filter"] = metadata_filter
        res = index.search(namespace=namespace, query=query)
        hits = res.get("result", {}).get("hits", []) if isinstance(res, dict) else res.result.hits
        out = []
        for h in hits:
            fields = h.get("fields", {}) if isinstance(h, dict) else getattr(h, "fields", {})
            hid = self._hit_field(h, "_id", "id", "id_")
            score = self._hit_field(h, "_score", "score", "score_")
            text_val = fields.pop("text", "") if isinstance(fields, dict) else ""
            out.append(MemoryHit(id=hid, score=float(score or 0.0), text=text_val, metadata=dict(fields)))
        return out

    def _query_vectors(self, index, namespace, vec, top_k, metadata_filter) -> list[MemoryHit]:
        res = index.query(
            namespace=namespace,
            vector=vec,
            top_k=top_k,
            include_metadata=True,
            filter=metadata_filter or None,
        )
        matches = res.get("matches", []) if isinstance(res, dict) else res.matches
        out = []
        for m in matches:
            meta = dict(m.get("metadata", {}) if isinstance(m, dict) else (m.metadata or {}))
            mid = m.get("id") if isinstance(m, dict) else m.id
            score = m.get("score") if isinstance(m, dict) else m.score
            text_val = meta.pop("text", "")
            out.append(MemoryHit(id=mid, score=float(score or 0.0), text=text_val, metadata=meta))
        return out

def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Pinecone metadata values must be str/number/bool/list[str]; drop None and
    coerce anything else to a string so an upsert never fails on a stray type."""
    clean: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)) or (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
        ):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean
