"""Low-level store builder.

Memory is configured **per user** (see ``services.memory_service``), so there is
no server-wide singleton here — just a helper that turns an explicit config into
a :class:`MemoryStore`, returning ``None`` if the SDK isn't installed.
"""

from __future__ import annotations

import logging

from .base import MemoryStore

_logger = logging.getLogger(__name__)


def build_pinecone_store(
    *,
    api_key: str,
    index_name: str,
    cloud: str = "aws",
    region: str = "us-east-1",
    embedder_kind: str = "pinecone",
    embed_model: str = "llama-text-embed-v2",
    openai_api_key: str | None = None,
    openai_embed_model: str = "text-embedding-3-small",
) -> MemoryStore | None:
    if not api_key:
        return None
    embedder = None
    if embedder_kind == "openai":
        if not openai_api_key:
            return None
        from .embedders import OpenAIEmbedder

        embedder = OpenAIEmbedder(openai_api_key, openai_embed_model)
    try:
        from .pinecone_store import PineconeMemoryStore

        return PineconeMemoryStore(
            api_key=api_key,
            index_name=index_name,
            embedder=embedder,
            embed_model=embed_model,
            cloud=cloud,
            region=region,
        )
    except ImportError:
        _logger.warning("pinecone package not installed; memory disabled (pip install pinecone)")
        return None
    except Exception as exc:  # noqa: BLE001 — never let memory init break a run
        _logger.warning("Failed to build memory store: %s", exc)
        return None
