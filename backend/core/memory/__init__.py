"""Modular vector-memory subsystem (episodic + inter-agent Q&A).

Public surface is the protocol types and the factory; concrete backends stay
behind ``factory.get_memory_store()``.
"""

from .base import Embedder, MemoryHit, MemoryRecord, MemoryStore
from .factory import get_memory_store, memory_enabled

__all__ = [
    "Embedder",
    "MemoryHit",
    "MemoryRecord",
    "MemoryStore",
    "get_memory_store",
    "memory_enabled",
]
