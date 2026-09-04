from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.settings import MemoryStatusResponse, SettingsBase, SettingsUpdate

_LEGACY_MEMORY_FIELDS = {
    "memory_store",
    "pinecone_index",
    "pinecone_cloud",
    "pinecone_region",
    "pinecone_embed_model",
}


def test_memory_settings_expose_only_mem0_embedder_configuration() -> None:
    fields = set(SettingsBase.model_fields)

    assert fields.isdisjoint(_LEGACY_MEMORY_FIELDS)
    assert {
        "memory_embedder",
        "memory_openai_embed_model",
        "memory_ollama_embed_model",
        "memory_recall_count",
        "agent_qa_enabled",
    }.issubset(fields)
    assert SettingsBase().memory_embedder == "openai"


def test_settings_update_rejects_retired_memory_fields() -> None:
    for field in _LEGACY_MEMORY_FIELDS:
        with pytest.raises(ValidationError):
            SettingsUpdate.model_validate({field: "legacy"})


def test_memory_embedder_rejects_retired_provider() -> None:
    with pytest.raises(ValidationError):
        SettingsUpdate(memory_embedder="pinecone")


def test_memory_status_contract_has_no_legacy_index() -> None:
    fields = set(MemoryStatusResponse.model_fields)

    assert "index" not in fields
    assert {"store", "embedder", "embed_model", "enabled"}.issubset(fields)
