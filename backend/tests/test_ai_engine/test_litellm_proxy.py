from backend.trading_agents.llm_clients.factory import create_llm_client
from backend.trading_agents.llm_clients.litellm_proxy_client import LiteLLMProxyClient


def test_factory_can_route_all_hosted_models_through_litellm(monkeypatch):
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://litellm.internal:4000")
    monkeypatch.setenv("LITELLM_PROXY_KEY", "proxy-key")
    monkeypatch.setenv("LITELLM_ROUTE_ALL", "true")
    client = create_llm_client("anthropic", "claude-sonnet-test", api_key="user-key")
    assert isinstance(client, LiteLLMProxyClient)
    assert client.base_url == "http://litellm.internal:4000/v1"
    assert client.proxy_api_key == "proxy-key"


def test_factory_keeps_ollama_local_when_litellm_enabled(monkeypatch):
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://litellm.internal:4000")
    monkeypatch.setenv("LITELLM_ROUTE_ALL", "true")
    client = create_llm_client("ollama", "local-model")
    assert not isinstance(client, LiteLLMProxyClient)
