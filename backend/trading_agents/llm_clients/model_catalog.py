from __future__ import annotations
from typing import Dict, List, Tuple
ModelOption = Tuple[str, str]
ProviderOptions = Dict[str, List[ModelOption]]
_GLM_MODELS: List[ModelOption] = [
    ("GLM-4 - Flagship model", "glm-4"),
    ("GLM-4-Flash - Fast, lightweight model", "glm-4-flash"),
]
_QWEN_MODELS: List[ModelOption] = [
    ("Qwen Plus - Balanced flagship model", "qwen-plus"),
    ("Qwen Turbo - Fast and efficient model", "qwen-turbo"),
]
_MINIMAX_MODELS: List[ModelOption] = [
    ("MiniMax abab6.5 - High performance chat model", "abab6.5-chat"),
]
MODEL_OPTIONS: ProviderOptions = {
    "openai": [
        ("GPT-4o - Flagship model, balanced speed and intelligence", "gpt-4o"),
        ("GPT-4o Mini - Lightweight and cost-efficient", "gpt-4o-mini"),
        ("o1 - Frontier reasoning model", "o1"),
        ("o1 Mini - Fast reasoning model", "o1-mini"),
        ("o3 Mini - Latest reasoning model", "o3-mini"),
    ],
    "anthropic": [
        ("Claude 3.5 Sonnet - Flagship, SOTA on agentic workflows", "claude-3-5-sonnet-latest"),
        ("Claude 3.5 Haiku - Balanced speed and intelligence", "claude-3-5-haiku-latest"),
        ("Claude 3 Opus - Previous frontier model", "claude-3-opus-20240229"),
    ],
    "google": [
        ("Gemini 1.5 Pro - Flagship, deep analytical reasoning", "gemini-1.5-pro"),
        ("Gemini 1.5 Flash - Lightweight and fast", "gemini-1.5-flash"),
        ("Gemini 2.0 Flash - Next-gen balanced speed and intelligence", "gemini-2.0-flash"),
    ],
    "xai": [
        ("Grok 2 - Flagship intelligence", "grok-2-1212"),
    ],
    "deepseek": [
        ("DeepSeek V3 - High performance cost-effective chat", "deepseek-chat"),
        ("DeepSeek R1 - Advanced reasoning and thinking", "deepseek-reasoner"),
    ],
    "qwen": _QWEN_MODELS,
    "qwen-cn": _QWEN_MODELS,
    "glm": _GLM_MODELS,
    "glm-cn": _GLM_MODELS,
    "minimax": _MINIMAX_MODELS,
    "minimax-cn": _MINIMAX_MODELS,
    "ollama": [
        ("Qwen3:latest (8B)", "qwen3:latest"),
        ("GPT-OSS:latest (20B)", "gpt-oss:latest"),
        ("GLM-4.7-Flash:latest (30B)", "glm-4.7-flash:latest"),
    ],
    "nvidia": [
        ("Llama-3.1 405B Instruct", "meta/llama-3.1-405b-instruct"),
        ("Llama-3.1 70B Instruct", "meta/llama-3.1-70b-instruct"),
        ("Llama-3.1 8B Instruct", "meta/llama-3.1-8b-instruct"),
        ("Llama-3.2 3B Instruct", "meta/llama-3.2-3b-instruct"),
    ],
    "litellm": [
        ("Default Model (e.g. gpt-4)", "gpt-4"),
        ("Default Quick Model (e.g. gpt-3.5-turbo)", "gpt-3.5-turbo"),
    ],
}
def get_model_options(provider: str, mode: str = "default") -> List[ModelOption]:
    return MODEL_OPTIONS.get(provider.lower(), [])
def get_known_models() -> Dict[str, List[str]]:
    return {
        provider: sorted({value for _, value in options})
        for provider, options in MODEL_OPTIONS.items()
    }
