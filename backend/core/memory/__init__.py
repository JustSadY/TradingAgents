"""Modular vector-memory subsystem (episodic + inter-agent Q&A).

Public surface is the protocol types plus ``build_pinecone_store``; per-user
resolution lives in ``services.memory_service.get_user_memory_store``.
"""

from .base import Embedder, MemoryHit, MemoryRecord, MemoryStore
from .factory import build_pinecone_store

__all__ = [
    "Embedder",
    "MemoryHit",
    "MemoryRecord",
    "MemoryStore",
    "build_pinecone_store",
]
