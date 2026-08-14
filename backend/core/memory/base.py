"""Modular vector-memory abstractions.

The trading engine's long-term memory is built on a small, pluggable interface
so the default Pinecone backend can be swapped for any other vector store, and
the embedding step can be done server-side (Pinecone hosted inference) or
client-side (e.g. OpenAI) without the callers caring.

Nothing here imports a concrete vendor SDK — see ``pinecone_store`` /
``embedders`` for implementations and ``factory`` for wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    """A single item to store. ``text`` is what gets embedded; ``metadata`` is
    returned verbatim on retrieval (and may be used for filtering)."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class MemoryHit:
    """A retrieval result."""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class Embedder(Protocol):
    """Turns text into vectors. Optional: a store may embed server-side instead
    (in which case the factory wires no embedder and the store handles it)."""

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

@runtime_checkable
class MemoryStore(Protocol):
    """A namespaced vector store. Implementations must be safe to call
    concurrently and should never raise for a missing namespace (treat as empty).
    """

    async def upsert(self, namespace: str, records: list[MemoryRecord]) -> None: ...

    async def query(
        self,
        namespace: str,
        text: str,
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryHit]: ...
