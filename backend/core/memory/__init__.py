"""Modular vector-memory subsystem (episodic + inter-agent Q&A).

Public surface is the protocol types plus the store builders
(``build_pinecone_store`` / ``build_pgvector_store``); per-user resolution
lives in ``services.memory_service.get_user_memory_store``.
"""

from .base import Embedder, MemoryHit, MemoryRecord, MemoryStore
from .factory import build_pgvector_store, build_pinecone_store

__all__ = [
    "Embedder",
    "MemoryHit",
    "MemoryRecord",
    "MemoryStore",
    "build_pgvector_store",
    "build_pinecone_store",
]
