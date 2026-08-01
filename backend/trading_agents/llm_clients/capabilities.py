from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StructuredMethod = Literal[
    "function_calling",
    "json_mode",
    "json_schema",
    "none",
]


@dataclass(frozen=True)
class ModelCapabilities:
    supports_tool_choice: bool
    supports_json_mode: bool
    supports_json_schema: bool
    preferred_structured_method: StructuredMethod
    requires_reasoning_content_roundtrip: bool = False
    requires_reasoning_split: bool = False
    # ``None`` means that Paperclip does not have a verified language list for
    # this exact model.  An empty set would mean that no natural-language
    # output is supported, so it is intentionally not used as a fallback.
    supported_output_languages: frozenset[str] | None = None


_DEFAULT = ModelCapabilities(
    supports_tool_choice=True,
    supports_json_mode=True,
    supports_json_schema=True,
    preferred_structured_method="function_calling",
)


# Source: NVIDIA's model card for Nemotron 3 Super.  Keep this mapping exact
# and narrow: it powers a user-facing warning, so unverified provider/model
# combinations must remain ``None`` rather than being guessed from a family
# name.  Turkish is deliberately absent from NVIDIA's published list.
_MODEL_CAPABILITIES: dict[str, ModelCapabilities] = {
    "nvidia/nemotron-3-super-120b-a12b": ModelCapabilities(
        supports_tool_choice=True,
        supports_json_mode=True,
        supports_json_schema=True,
        preferred_structured_method="function_calling",
        supported_output_languages=frozenset(
            {"English", "French", "German", "Italian", "Japanese", "Spanish", "Chinese"}
        ),
    ),
}


def get_capabilities(model_name: str) -> ModelCapabilities:
    """Return verified capabilities for an exact model ID when available."""
    normalized = model_name.strip().casefold() if isinstance(model_name, str) else ""
    return _MODEL_CAPABILITIES.get(normalized, _DEFAULT)


def get_supported_output_languages(model_name: str) -> list[str] | None:
    """Return a sorted verified language list, or ``None`` when unknown."""
    languages = get_capabilities(model_name).supported_output_languages
    return sorted(languages) if languages is not None else None


def supports_output_language(model_name: str, language: str) -> bool | None:
    """Check an output language without treating unknown support as failure."""
    languages = get_capabilities(model_name).supported_output_languages
    if languages is None:
        return None
    return isinstance(language, str) and language.strip().casefold() in {item.casefold() for item in languages}
