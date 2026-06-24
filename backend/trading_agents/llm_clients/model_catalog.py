from __future__ import annotations

from .registry import llm_registry

ModelOption = tuple[str, str]


def get_model_options(provider: str, _mode: str = "default") -> list[ModelOption]:
    return llm_registry.get_model_options(provider)


def get_known_models() -> dict[str, list[str]]:
    return {p.key: sorted({value for _, value in p.models}) for p in llm_registry.list_providers()}
