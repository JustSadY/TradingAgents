from backend.trading_agents.llm_clients.base_client import (
    is_quota_exhausted,
    is_rate_limited,
    normalize_content,
    classify_error,
)


class _FakeResponse:
    def __init__(self, content):
        self.content = content


def test_normalize_content_passthrough_string():
    result = normalize_content(_FakeResponse("hello"))
    assert result.content == "hello"


def test_normalize_content_aimessage():
    from langchain_core.messages import AIMessage

    result = normalize_content(_FakeResponse(AIMessage(content="world")))
    assert isinstance(result, _FakeResponse)
    assert result.content.content == "world"


def test_normalize_content_list_of_text_blocks():
    result = normalize_content(_FakeResponse(
        [{"type": "text", "text": "block1"}, {"type": "text", "text": "block2"}]
    ))
    assert result.content == "block1\nblock2"


def test_is_quota_exhausted_detects_resourceexhausted():
    exc = Exception("resourceexhausted: quota exceeded")
    assert is_quota_exhausted(exc) is True


def test_is_quota_exhausted_detects_insufficient_quota():
    exc = Exception("insufficient_quota")
    assert is_quota_exhausted(exc) is True


def test_is_quota_exhausted_ignores_other_errors():
    exc = Exception("connection timeout")
    assert is_quota_exhausted(exc) is False


def test_is_rate_limited_detects_429():
    exc = Exception("429 Too Many Requests")
    assert is_rate_limited(exc) is True


def test_is_rate_limited_detects_rate_limit():
    exc = Exception("rate limit exceeded")
    assert is_rate_limited(exc) is True


def test_is_rate_limited_ignores_generic_errors():
    exc = Exception("internal server error")
    assert is_rate_limited(exc) is False


def test_classify_error_quota_exhausted():
    assert classify_error(Exception("resourceexhausted")) == "quota_exhausted"


def test_classify_error_rate_limited():
    # "429" is now caught by is_quota_exhausted before is_rate_limited
    assert classify_error(Exception("retry after 5 seconds")) == "rate_limited"


def test_classify_error_auth():
    assert classify_error(Exception("401 unauthorized")) == "auth"


def test_classify_error_timeout():
    assert classify_error(Exception("timeout")) == "timeout"


def test_classify_error_unknown():
    assert classify_error(Exception("random gibberish")) == "unknown"
