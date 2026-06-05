from __future__ import annotations
from typing import Optional
from .registry import llm_registry

def get_api_key_env(provider: str) -> Optional[str]:
    p = llm_registry.get(provider)
    return p.api_key_env if p else None
