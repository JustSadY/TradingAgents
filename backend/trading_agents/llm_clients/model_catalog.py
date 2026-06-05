from __future__ import annotations
from typing import Dict, List, Tuple
from .registry import llm_registry

ModelOption = Tuple[str, str]

def get_model_options(provider: str, mode: str = "default") -> List[ModelOption]:
    return llm_registry.get_model_options(provider)

def get_known_models() -> Dict[str, List[str]]:
    return {
        p.key: sorted({value for _, value in p.models})
        for p in llm_registry.list_providers()
    }
