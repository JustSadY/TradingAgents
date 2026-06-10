from uuid import uuid4
import pytest
from unittest.mock import AsyncMock
from backend.services.stats_handler import StatsCallbackHandler
from backend.services.analysis.streaming_handler import TokenStreamingCallbackHandler


class MockResponse:
    def __init__(self, usage):
        self.usage_metadata = usage


def test_stats_callback_handler_token_counting():
    handler = StatsCallbackHandler()
    
    # First LLM call
    run_id_1 = uuid4()
    resp1 = MockResponse({"prompt_tokens": 100, "completion_tokens": 50})
    handler.on_llm_end(resp1, run_id=run_id_1)
    
    assert handler.tokens_in == 100
    assert handler.tokens_out == 50
    
    # Simulate streaming callback invoking on_llm_end multiple times for run_id_1
    resp1_updated = MockResponse({"prompt_tokens": 100, "completion_tokens": 55})
    handler.on_llm_end(resp1_updated, run_id=run_id_1)
    
    assert handler.tokens_in == 100
    assert handler.tokens_out == 55  # Overwritten, not added!
    
    # Second LLM call
    run_id_2 = uuid4()
    resp2 = MockResponse({"prompt_tokens": 200, "completion_tokens": 80})
    handler.on_llm_end(resp2, run_id=run_id_2)
    
    assert handler.tokens_in == 300
    assert handler.tokens_out == 135


@pytest.mark.asyncio
async def test_token_streaming_callback_handler_token_counting():
    mock_emitter = AsyncMock()
    handler = TokenStreamingCallbackHandler(emitter=mock_emitter)
    
    # First LLM call
    run_id_1 = uuid4()
    resp1 = MockResponse({"prompt_tokens": 100, "completion_tokens": 50})
    await handler.on_llm_end(resp1, run_id=run_id_1)
    
    assert handler.tokens_in == 100
    assert handler.tokens_out == 50
    
    # Stream update for the same run_id_1
    resp1_updated = MockResponse({"prompt_tokens": 100, "completion_tokens": 60})
    await handler.on_llm_end(resp1_updated, run_id=run_id_1)
    
    assert handler.tokens_in == 100
    assert handler.tokens_out == 60
    
    # Second LLM call
    run_id_2 = uuid4()
    resp2 = MockResponse({"prompt_tokens": 150, "completion_tokens": 70})
    await handler.on_llm_end(resp2, run_id=run_id_2)
    
    assert handler.tokens_in == 250
    assert handler.tokens_out == 130
