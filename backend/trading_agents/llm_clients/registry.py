from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMProvider:
    key: str
    label: str
    models: list[tuple[str, str]] = field(default_factory=list)
    effort_options: list[dict[str, str]] = field(default_factory=list)
    is_openai_compatible: bool = False

    def get_api_key(self) -> str | None:
        # Explicitly removed .env lookup
        return None


class LLMProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider):
        self._providers[provider.key.lower()] = provider

    def get(self, key: str) -> LLMProvider | None:
        return self._providers.get(key.lower())

    def list_providers(self) -> list[LLMProvider]:
        # Return in a specific order for the UI
        order = ["openai", "anthropic", "google", "nvidia"]
        return [self._providers[k] for k in order if k in self._providers]

    def get_provider_labels(self) -> dict[str, str]:
        return {p.key: p.label for p in self.list_providers()}

    def get_effort_options(self) -> dict[str, list[dict[str, str]]]:
        return {p.key: p.effort_options for p in self.list_providers() if p.effort_options}

    def get_model_options(self, key: str) -> list[tuple[str, str]]:
        p = self.get(key)
        return p.models if p else []

    def is_openai_compatible(self, key: str) -> bool:
        p = self.get(key)
        return p.is_openai_compatible if p else False


# Global registry instance
llm_registry = LLMProviderRegistry()

# Standard effort options
_STANDARD_EFFORT = [
    {"value": "low", "label": "Low"},
    {"value": "medium", "label": "Medium"},
    {"value": "high", "label": "High"},
]

# Register core supported providers (NO api_key_env defined)
llm_registry.register(
    LLMProvider(
        key="openai",
        label="OpenAI",
        is_openai_compatible=True,
        effort_options=_STANDARD_EFFORT,
        models=[
            ("GPT-4o - Flagship model, balanced speed and intelligence", "gpt-4o"),
            ("GPT-4o Mini - Lightweight and cost-efficient", "gpt-4o-mini"),
            ("o1 - Frontier reasoning model", "o1"),
            ("o1 Mini - Fast reasoning model", "o1-mini"),
            ("o3 Mini - Latest reasoning model", "o3-mini"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="anthropic",
        label="Anthropic (Claude)",
        effort_options=_STANDARD_EFFORT,
        models=[
            ("Claude 3.5 Sonnet - Flagship, SOTA on agentic workflows", "claude-3-5-sonnet-latest"),
            ("Claude 3.5 Haiku - Balanced speed and intelligence", "claude-3-5-haiku-latest"),
            ("Claude 3 Opus - Previous frontier model", "claude-3-opus-20240229"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="google",
        label="Google (Gemini)",
        effort_options=[
            {"value": "minimal", "label": "Minimal"},
            {"value": "low", "label": "Low"},
            {"value": "medium", "label": "Medium"},
            {"value": "high", "label": "High"},
        ],
        models=[
            ("Gemini 1.5 Pro - Flagship, deep analytical reasoning", "gemini-1.5-pro"),
            ("Gemini 1.5 Flash - Lightweight and fast", "gemini-1.5-flash"),
            ("Gemini 2.0 Flash - Next-gen balanced speed and intelligence", "gemini-2.0-flash"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="nvidia",
        label="NVIDIA NIM",
        is_openai_compatible=True,
        models=[
            ("Llama-3.1-Nemotron-70B-Instruct", "nvidia/llama-3.1-nemotron-70b-instruct"),
            ("Nemotron-4 340B Instruct", "nvidia/nemotron-4-340b-instruct"),
            ("Llama-3.1 405B Instruct", "meta/llama-3.1-405b-instruct"),
            ("Llama-3.1 70B Instruct", "meta/llama-3.1-70b-instruct"),
            ("Llama-3.1 8B Instruct", "meta/llama-3.1-8b-instruct"),
            ("Llama-3.2 3B Instruct", "meta/llama-3.2-3b-instruct"),
        ],
    )
)
