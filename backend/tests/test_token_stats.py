"""Tests for LLM token-usage extraction (per-analysis token counters).

Regression coverage for two real-world undercounting bugs:
- Anthropic's raw usage dict reports cached prompt tokens in separate buckets
  (cache_read/cache_creation_input_tokens); with prompt caching enabled the
  counters missed most of the input unless those are added back.
- The extractor preferred the raw llm_output dict over LangChain's normalized
  usage_metadata, so the under-reporting raw source won when both were present.
"""

from types import SimpleNamespace

from backend.services.stats_handler import StatsCallbackHandler


def test_openai_style_prompt_tokens():
    usage = StatsCallbackHandler._parse_usage_dict({"prompt_tokens": 120, "completion_tokens": 30})
    assert usage == {"input": 120, "output": 30}


def test_anthropic_raw_usage_includes_cache_buckets():
    # Raw Anthropic usage with caching: input_tokens excludes the cached prefix.
    usage = StatsCallbackHandler._parse_usage_dict(
        {
            "input_tokens": 200,  # uncached remainder only
            "cache_read_input_tokens": 4800,
            "cache_creation_input_tokens": 1000,
            "output_tokens": 350,
        }
    )
    assert usage == {"input": 6000, "output": 350}


def test_empty_usage_returns_none():
    assert StatsCallbackHandler._parse_usage_dict({}) is None
    assert StatsCallbackHandler._parse_usage_dict(None) is None
    assert StatsCallbackHandler._parse_usage_dict({"prompt_tokens": 0, "completion_tokens": 0}) is None


def test_normalized_usage_metadata_preferred_over_raw_llm_output():
    # The message carries LangChain's normalized totals (cache included); the
    # raw llm_output carries the Anthropic under-count. Normalized must win.
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 6000, "output_tokens": 350},
        response_metadata={},
    )
    response = SimpleNamespace(
        llm_output={"usage": {"input_tokens": 200, "output_tokens": 350}},
        usage_metadata=None,
        generations=[[SimpleNamespace(message=message)]],
    )
    usage = StatsCallbackHandler._extract_usage(response)
    assert usage == {"input": 6000, "output": 350}


def test_llm_output_still_used_as_fallback():
    response = SimpleNamespace(
        llm_output={"token_usage": {"prompt_tokens": 90, "completion_tokens": 10}},
        usage_metadata=None,
        generations=[],
    )
    usage = StatsCallbackHandler._extract_usage(response)
    assert usage == {"input": 90, "output": 10}


def test_handler_accumulates_across_calls():
    handler = StatsCallbackHandler()
    r1 = SimpleNamespace(
        llm_output=None,
        usage_metadata=None,
        generations=[[SimpleNamespace(message=SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 20}, response_metadata={}))]],
    )
    r2 = SimpleNamespace(
        llm_output=None,
        usage_metadata=None,
        generations=[[SimpleNamespace(message=SimpleNamespace(usage_metadata={"input_tokens": 50, "output_tokens": 5}, response_metadata={}))]],
    )
    handler.on_llm_end(r1)
    handler.on_llm_end(r2)
    stats = handler.get_stats()
    assert stats["tokens_in"] == 150
    assert stats["tokens_out"] == 25
