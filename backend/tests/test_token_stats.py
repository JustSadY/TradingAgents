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
        generations=[
            [
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={"input_tokens": 100, "output_tokens": 20}, response_metadata={}
                    )
                )
            ]
        ],
    )
    r2 = SimpleNamespace(
        llm_output=None,
        usage_metadata=None,
        generations=[
            [
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={"input_tokens": 50, "output_tokens": 5}, response_metadata={}
                    )
                )
            ]
        ],
    )
    handler.on_llm_end(r1)
    handler.on_llm_end(r2)
    stats = handler.get_stats()
    assert stats["tokens_in"] == 150
    assert stats["tokens_out"] == 25


def _chunk(text, usage=None):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    return ChatGenerationChunk(message=AIMessageChunk(content=text, usage_metadata=usage))


def _merge(chunks):
    merged = None
    for c in chunks:
        merged = c if merged is None else merged + c
    return merged


def _filter_keep_last_usage(chunks):
    """Mirror NormalizedChatOpenAI's stream filtering for unit testing."""
    from backend.trading_agents.llm_clients.openai_client import _final_usage_chunk, _strip_chunk_usage

    last = None
    out = []
    for c in chunks:
        usage = _strip_chunk_usage(c)
        if usage is not None:
            last = usage
        out.append(c)
    if last is not None:
        out.append(_final_usage_chunk(last))
    return out


def test_cumulative_per_chunk_usage_not_inflated():
    # Provider emits CUMULATIVE usage on every chunk (DeepSeek/Qwen style):
    # without filtering, merging sums to 15k input; with filtering, the last
    # snapshot (the true total) survives alone.
    usage = lambda i, o: {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}  # noqa: E731
    chunks = [_chunk("a", usage(5000, 1)), _chunk("b", usage(5000, 2)), _chunk("c", usage(5000, 3))]

    inflated = _merge([_chunk(c.message.content, dict(c.message.usage_metadata)) for c in chunks])
    assert inflated.message.usage_metadata["input_tokens"] == 15000  # the bug

    merged = _merge(_filter_keep_last_usage(chunks))
    assert merged.message.usage_metadata["input_tokens"] == 5000
    assert merged.message.usage_metadata["output_tokens"] == 3
    assert merged.message.content == "abc"


def test_final_only_usage_unchanged():
    # Real OpenAI behaviour: usage arrives once on the final (empty) chunk.
    chunks = [
        _chunk("a"),
        _chunk("b"),
        _chunk("", {"input_tokens": 800, "output_tokens": 40, "total_tokens": 840}),
    ]
    merged = _merge(_filter_keep_last_usage(chunks))
    assert merged.message.usage_metadata["input_tokens"] == 800
    assert merged.message.usage_metadata["output_tokens"] == 40


def test_no_usage_stream_stays_usageless():
    merged = _merge(_filter_keep_last_usage([_chunk("a"), _chunk("b")]))
    assert merged.message.usage_metadata is None


def test_cumulative_response_metadata_and_generation_info_stripped():
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    def usage(i, o):
        return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}

    # Simulate chunks where provider embeds cumulative usage in response_metadata and generation_info
    chunks = [
        ChatGenerationChunk(
            message=AIMessageChunk(content="a", response_metadata={"token_usage": usage(1000, 1)}),
            generation_info={"token_usage": usage(1000, 1)}
        ),
        ChatGenerationChunk(
            message=AIMessageChunk(content="b", response_metadata={"token_usage": usage(1000, 2)}),
            generation_info={"token_usage": usage(1000, 2)}
        ),
        ChatGenerationChunk(
            message=AIMessageChunk(content="c", response_metadata={"token_usage": usage(1000, 3)}),
            generation_info={"token_usage": usage(1000, 3)}
        ),
    ]

    filtered = _filter_keep_last_usage(chunks)
    merged = _merge(filtered)

    # The final merged chunk should have the correct un-accumulated totals in usage_metadata
    assert merged.message.usage_metadata["input_tokens"] == 1000
    assert merged.message.usage_metadata["output_tokens"] == 3

    # response_metadata and generation_info should have been stripped and thus not summed up
    assert "token_usage" not in (merged.message.response_metadata or {})
    assert "token_usage" not in (merged.generation_info or {})

