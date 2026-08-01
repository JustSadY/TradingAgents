from __future__ import annotations

from dataclasses import dataclass, field

@dataclass(frozen=True)
class LLMProvider:
    key: str
    label: str
    models: list[tuple[str, str]] = field(default_factory=list)
    effort_options: list[dict[str, str]] = field(default_factory=list)
    is_openai_compatible: bool = False
    requires_api_key: bool = True

    def get_api_key(self) -> str | None:
        return None

class LLMProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider):
        self._providers[provider.key.lower()] = provider

    def get(self, key: str) -> LLMProvider | None:
        return self._providers.get(key.lower())

    def list_providers(self) -> list[LLMProvider]:
        order = ["openai", "anthropic", "google", "mistral", "groq", "nvidia", "deepseek", "ollama"]
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

    def provider_requires_api_key(self, key: str) -> bool:
        """Whether a provider expects a tenant-owned credential.

        Unknown providers default to requiring a key so a missing registry
        entry can never accidentally bypass authentication checks.
        """
        p = self.get(key) if isinstance(key, str) else None
        return p.requires_api_key if p is not None else True

def provider_requires_api_key(provider: str) -> bool:
    """Return the canonical tenant-credential policy for ``provider``."""
    return llm_registry.provider_requires_api_key(provider)

llm_registry = LLMProviderRegistry()

_STANDARD_EFFORT = [
    {"value": "low", "label": "Low"},
    {"value": "medium", "label": "Medium"},
    {"value": "high", "label": "High"},
]

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
            ("Nemotron 3 Super 120B A12B", "nvidia/nemotron-3-super-120b-a12b"),
            ("Llama-3.1-Nemotron-70B-Instruct", "nvidia/llama-3.1-nemotron-70b-instruct"),
            ("Nemotron-4 340B Instruct", "nvidia/nemotron-4-340b-instruct"),
            ("Llama-3.1 405B Instruct", "meta/llama-3.1-405b-instruct"),
            ("Llama-3.1 70B Instruct", "meta/llama-3.1-70b-instruct"),
            ("Llama-3.1 8B Instruct", "meta/llama-3.1-8b-instruct"),
            ("Llama-3.2 3B Instruct", "meta/llama-3.2-3b-instruct"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="mistral",
        label="Mistral AI",
        effort_options=_STANDARD_EFFORT,
        models=[
            ("Mistral Large - Flagship, state-of-the-art reasoning", "mistral-large-latest"),
            ("Mistral Small - Fast and cost-efficient", "mistral-small-latest"),
            ("Codestral - Code generation specialist", "codestral-latest"),
            ("Open Mistral Nemo - Open-weight balanced model", "open-mistral-nemo"),
            ("Open Mixtral 8x22B - High-capacity MoE", "open-mixtral-8x22b"),
            ("Open Mixtral 8x7B - Efficient MoE", "open-mixtral-8x7b"),
            ("Open Mistral 7B - Lightweight open model", "open-mistral-7b"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="groq",
        label="Groq (Fast Inference)",
        effort_options=_STANDARD_EFFORT,
        models=[
            ("Llama 3.3 70B - Fast inference via Groq", "llama-3.3-70b-versatile"),
            ("Llama 3.1 70B - Groq-hosted versatile model", "llama-3.1-70b-versatile"),
            ("Llama 3.1 8B - Fast and lightweight", "llama-3.1-8b-instant"),
            ("Llama Guard 3 8B - Safety classification", "llama-guard-3-8b"),
            ("Mixtral 8x7B - Efficient MoE on Groq", "mixtral-8x7b-32768"),
            ("Gemma 2 9B - Google's efficient model", "gemma2-9b-it"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="deepseek",
        label="DeepSeek",
        is_openai_compatible=True,
        effort_options=_STANDARD_EFFORT,
        models=[
            ("DeepSeek V3 - Flagship, state-of-the-art reasoning", "deepseek-chat"),
            ("DeepSeek R1 - Advanced reasoning with chain-of-thought", "deepseek-reasoner"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="ollama",
        label="Ollama (Local)",
        is_openai_compatible=True,
        requires_api_key=False,
        models=[
            ("Llama 3.3 70B - Meta's latest 70B instruction model", "llama3.3"),
            ("Llama 3.2 3B - Fast and lightweight", "llama3.2"),
            ("Llama 3.1 8B - Balanced speed and quality", "llama3.1"),
            ("Llama 3.1 70B - High-quality 70B model", "llama3.1:70b"),
            ("Gemma 3 27B - Google's open model", "gemma3:27b"),
            ("Gemma 3 12B - Compact Google model", "gemma3:12b"),
            ("Qwen 2.5 72B - Alibaba's flagship open model", "qwen2.5:72b"),
            ("Qwen 2.5 14B - Mid-size Qwen model", "qwen2.5:14b"),
            ("DeepSeek R1 32B - Reasoning model", "deepseek-r1:32b"),
            ("DeepSeek R1 14B - Compact reasoning model", "deepseek-r1:14b"),
            ("Mistral 7B - Fast general-purpose model", "mistral"),
            ("Phi-4 14B - Microsoft's small capable model", "phi4"),
        ],
    )
)
