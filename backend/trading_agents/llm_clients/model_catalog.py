from __future__ import annotations
from typing import Dict, List, Tuple
ModelOption = Tuple[str, str]
ProviderOptions = Dict[str, List[ModelOption]]
_GLM_MODELS: List[ModelOption] = [
    ("GLM-5.1 - Latest flagship, 204K ctx", "glm-5.1"),
    ("GLM-5 - Flagship, 204K ctx", "glm-5"),
    ("GLM-5-Turbo - Fast, switchable thinking modes", "glm-5-turbo"),
    ("GLM-4.7 - Previous-gen flagship", "glm-4.7"),
    ("GLM-4.5-Air - Lightweight, cost-efficient", "glm-4.5-air"),
]
_QWEN_MODELS: List[ModelOption] = [
    ("Qwen 3.6 Plus - Flagship vision-language, agentic coding SOTA", "qwen3.6-plus"),
    ("Qwen 3.6 Flash - Latest fast, agentic coding + vision-language", "qwen3.6-flash"),
    ("Qwen 3.5 Plus - Previous-gen flagship", "qwen3.5-plus"),
    ("Qwen 3.5 Flash - Previous-gen fast", "qwen3.5-flash"),
    ("Qwen 3 Max - Specialized for agent programming + tool use", "qwen3-max"),
]
_MINIMAX_MODELS: List[ModelOption] = [
    ("MiniMax-M2.7 - Flagship, SOTA on coding/agent benchmarks, 204K ctx", "MiniMax-M2.7"),
    ("MiniMax-M2.7-highspeed - Same quality as M2.7, ~100 TPS", "MiniMax-M2.7-highspeed"),
    ("MiniMax-M2.5 - Previous-gen flagship, 204K ctx", "MiniMax-M2.5"),
    ("MiniMax-M2.5-highspeed - Previous-gen highspeed, 204K ctx", "MiniMax-M2.5-highspeed"),
    ("MiniMax-M2.1 - Earlier M2 line, 204K ctx", "MiniMax-M2.1"),
    ("MiniMax-M2.1-highspeed - M2.1 highspeed, 204K ctx", "MiniMax-M2.1-highspeed"),
    ("MiniMax-M2 - Base M2, 204K ctx", "MiniMax-M2"),
]
MODEL_OPTIONS: ProviderOptions = {
    "openai": [
        ("GPT-5.5 Pro - Most capable, expensive ($30/$180 per 1M tokens)", "gpt-5.5-pro"),
        ("GPT-5.5 - Latest frontier, 1M context", "gpt-5.5"),
        ("GPT-5.4 - Previous-gen frontier, 1M context, cost-effective", "gpt-5.4"),
        ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
        ("GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"),
        ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
        ("GPT-4.1 - Smartest non-reasoning model", "gpt-4.1"),
    ],
    "anthropic": [
        ("Claude Opus 4.7 - Latest frontier, long-running agents and coding", "claude-opus-4-7"),
        ("Claude Opus 4.6 - Frontier intelligence, agents and coding", "claude-opus-4-6"),
        ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
        ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
        ("Claude Sonnet 4.5 - High-performance for agents and coding", "claude-sonnet-4-5"),
        ("Claude Haiku 4.5 - Fastest with near-frontier intelligence", "claude-haiku-4-5"),
    ],
    "google": [
        ("Gemini 3.1 Pro - Reasoning-first, complex workflows (preview)", "gemini-3.1-pro-preview"),
        ("Gemini 3.1 Flash Lite - Most cost-efficient (GA)", "gemini-3.1-flash-lite"),
        ("Gemini 3 Flash - Next-gen fast (preview)", "gemini-3-flash-preview"),
        ("Gemini 2.5 Pro - Stable pro model", "gemini-2.5-pro"),
        ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
        ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
    ],
    "xai": [
        ("Grok 4.20 (Reasoning) - Latest frontier reasoning model", "grok-4.20-reasoning"),
        ("Grok 4.20 (Non-Reasoning) - Latest, speed-optimized", "grok-4.20-non-reasoning"),
        ("Grok 4.20 - Auto-select reasoning behavior", "grok-4.20"),
        ("Grok 4 Fast (Reasoning) - High-performance", "grok-4-fast-reasoning"),
        ("Grok 4 Fast (Non-Reasoning) - Speed optimized", "grok-4-fast-non-reasoning"),
        ("Grok 4 - Flagship (dated build)", "grok-4-0709"),
    ],
    "deepseek": [
        ("DeepSeek V4 Pro - Latest V4 flagship model", "deepseek-v4-pro"),
        ("DeepSeek V4 Flash - Latest V4 fast model", "deepseek-v4-flash"),
        ("DeepSeek V3.2 (thinking)", "deepseek-reasoner"),
        ("DeepSeek V3.2", "deepseek-chat"),
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
