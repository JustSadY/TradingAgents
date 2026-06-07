"""Single wiring point for the memory backend.

Callers depend on the :class:`MemoryStore` protocol, never on a concrete vendor,
so swapping backends means editing only this module. Returns ``None`` when memory
isn't configured (no Pinecone key) — callers must treat that as "memory off".
"""

from __future__ import annotations

import logging
from functools import lru_cache

from backend.core.config import get_settings

from .base import Embedder, MemoryStore

_logger = logging.getLogger(__name__)


def _build_embedder(settings) -> Embedder | None:
    if settings.MEMORY_EMBEDDER == "openai":
        if not settings.MEMORY_OPENAI_API_KEY:
            _logger.warning("MEMORY_EMBEDDER=openai but MEMORY_OPENAI_API_KEY is unset; memory disabled")
            return None
        from .embedders import OpenAIEmbedder

        return OpenAIEmbedder(settings.MEMORY_OPENAI_API_KEY, settings.MEMORY_OPENAI_EMBED_MODEL)
    return None  # default: Pinecone hosted inference (server-side embedding)


@lru_cache
def get_memory_store() -> MemoryStore | None:
    """Return the configured memory store, or ``None`` if memory is off."""
    settings = get_settings()
    if settings.MEMORY_BACKEND != "pinecone":
        _logger.warning("Unknown MEMORY_BACKEND %r; memory disabled", settings.MEMORY_BACKEND)
        return None
    if not settings.PINECONE_API_KEY:
        return None  # memory disabled — no fallback by design

    if settings.MEMORY_EMBEDDER == "openai" and not settings.MEMORY_OPENAI_API_KEY:
        return None

    try:
        from .pinecone_store import PineconeMemoryStore

        return PineconeMemoryStore(
            api_key=settings.PINECONE_API_KEY,
            index_name=settings.PINECONE_INDEX,
            embedder=_build_embedder(settings),
            embed_model=settings.PINECONE_EMBED_MODEL,
            cloud=settings.PINECONE_CLOUD,
            region=settings.PINECONE_REGION,
        )
    except ImportError:
        _logger.warning("pinecone package not installed; memory disabled (pip install pinecone)")
        return None
    except Exception as exc:  # noqa: BLE001 — never let memory init break startup
        _logger.warning("Failed to initialize memory store: %s", exc)
        return None


def memory_enabled() -> bool:
    return get_memory_store() is not None
