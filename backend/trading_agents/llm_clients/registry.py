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
            ("GPT-5.6 Sol - Frontier model for complex professional work", "gpt-5.6-sol"),
            ("GPT-5.6 Terra - Balances intelligence and cost", "gpt-5.6-terra"),
            ("GPT-5.6 Luna - Fastest and most affordable", "gpt-5.6-luna"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="anthropic",
        label="Anthropic (Claude)",
        effort_options=_STANDARD_EFFORT,
        models=[
            ("Claude Opus 5 - Flagship, complex agentic and enterprise work", "claude-opus-5"),
            ("Claude Sonnet 5 - Best combination of speed and intelligence", "claude-sonnet-5"),
            ("Claude Fable 5 - Next-generation intelligence for long-running agents", "claude-fable-5"),
            ("Claude Haiku 4.5 - Fastest, near-frontier intelligence", "claude-haiku-4-5"),
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
            ("Gemini 3.7 Flash - Latest Flash, complex coding and agentic workflows", "gemini-3.7-flash"),
            ("Gemini 3.1 Pro (Preview) - Flagship, deep analytical reasoning", "gemini-3.1-pro-preview"),
            ("Gemini 3.6 Flash - Balanced speed across everyday tasks", "gemini-3.6-flash"),
            ("Gemini 3.5 Flash Lite - Fastest and most cost-effective", "gemini-3.5-flash-lite"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="nvidia",
        label="NVIDIA NIM",
        is_openai_compatible=True,
        # TODO: not re-verified against the current NIM catalog at
        # https://build.nvidia.com/models — the Llama 3.1/3.2 entries below
        # predate the Nemotron 3 generation and may no longer be served.
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
            ("Mistral Medium 3.5 - Frontier-class, agentic and coding", "mistral-medium-3-5-26-04"),
            ("Mistral Large 3 - Open-weight general-purpose multimodal", "mistral-large-3-25-12"),
            ("Mistral Small 4 - Unified instruct, reasoning and coding", "mistral-small-4-0-26-03"),
            ("Ministral 3 14B - Compact text and vision model", "ministral-3-14b-25-12"),
            ("Ministral 3 8B - Efficient text and vision model", "ministral-3-8b-25-12"),
            ("Ministral 3 3B - Lightweight text and vision model", "ministral-3-3b-25-12"),
            ("Codestral - Code generation specialist", "codestral-latest"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="groq",
        label="Groq (Fast Inference)",
        effort_options=_STANDARD_EFFORT,
        models=[
            ("GPT-OSS 120B - Flagship open-weight model on Groq", "openai/gpt-oss-120b"),
            ("GPT-OSS 20B - Highest throughput on Groq", "openai/gpt-oss-20b"),
            ("Groq Compound - Built-in web search and code execution", "groq/compound"),
            ("Groq Compound Mini - Lighter Compound variant", "groq/compound-mini"),
            ("Qwen3.6 27B (Preview) - Multilingual open model", "qwen/qwen3.6-27b"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="deepseek",
        label="DeepSeek",
        is_openai_compatible=True,
        effort_options=_STANDARD_EFFORT,
        # The legacy ``deepseek-chat`` / ``deepseek-reasoner`` aliases were
        # discontinued on 2026-07-24 and now return an error.
        models=[
            ("DeepSeek V4 Pro - Flagship, 1M context, thinking mode", "deepseek-v4-pro"),
            ("DeepSeek V4 Flash - Fast and cost-efficient", "deepseek-v4-flash"),
        ],
    )
)

llm_registry.register(
    LLMProvider(
        key="ollama",
        label="Ollama (Local)",
        is_openai_compatible=True,
        requires_api_key=False,
        # Ollama tags are resolved against the user's local install, so these
        # are suggestions rather than a hosted catalog; any pulled tag works.
        models=[
            ("Qwen3.6 27B - Agentic coding and reasoning", "qwen3.6:27b"),
            ("Qwen3 14B - Mid-size general-purpose model", "qwen3:14b"),
            ("Gemma 4 27B - Google's open model", "gemma4:27b"),
            ("Gemma 4 12B - Compact Google model", "gemma4:12b"),
            ("Llama 3.3 70B - Meta's 70B instruction model", "llama3.3"),
            ("DeepSeek R1 32B - Reasoning model", "deepseek-r1:32b"),
            ("DeepSeek R1 14B - Compact reasoning model", "deepseek-r1:14b"),
            ("Mistral 7B - Fast general-purpose model", "mistral"),
        ],
    )
)
