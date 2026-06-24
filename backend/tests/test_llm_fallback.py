"""Tests for invocation-time LLM provider failover (FallbackLLM)."""

from langchain_core.runnables import RunnableLambda

from backend.trading_agents.llm_clients.fallback import FallbackLLM


class _FakeChatModel(RunnableLambda):
    def __init__(self, reply: str, *, fail: bool = False):
        self.reply = reply
        self.fail = fail
        self.bound_tools = None
        self.structured_schema = None
        super().__init__(self._call)

    def _call(self, _input):
        if self.fail:
            raise RuntimeError("provider down")
        return self.reply

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = list(tools)
        return RunnableLambda(self._call)

    def with_structured_output(self, schema, **kwargs):
        self.structured_schema = schema
        return RunnableLambda(self._call)


def test_primary_used_when_healthy():
    llm = FallbackLLM(_FakeChatModel("primary"), _FakeChatModel("fallback"))
    assert llm.invoke({}) == "primary"


async def test_failover_on_primary_error():
    llm = FallbackLLM(_FakeChatModel("primary", fail=True), _FakeChatModel("fallback"))
    assert llm.invoke({}) == "fallback"
    assert await llm.ainvoke({}) == "fallback"


def test_bind_tools_applies_to_both_and_fails_over():
    primary = _FakeChatModel("primary", fail=True)
    fallback = _FakeChatModel("fallback")
    bound = FallbackLLM(primary, fallback).bind_tools(["tool_a"])

    assert bound.invoke({}) == "fallback"
    assert primary.bound_tools == ["tool_a"]
    assert fallback.bound_tools == ["tool_a"]


def test_structured_output_applies_to_both_and_fails_over():
    primary = _FakeChatModel("primary", fail=True)
    fallback = _FakeChatModel("fallback")
    structured = FallbackLLM(primary, fallback).with_structured_output(dict)

    assert structured.invoke({}) == "fallback"
    assert primary.structured_schema is dict
    assert fallback.structured_schema is dict


def test_with_config_preserves_fallback_wrapper():
    llm = FallbackLLM(_FakeChatModel("primary", fail=True), _FakeChatModel("fallback"))
    configured = llm.with_config(tags=["agent-x"])

    assert isinstance(configured, FallbackLLM)
    assert configured.invoke({}) == "fallback"


def test_unknown_attributes_delegate_to_primary():
    llm = FallbackLLM(_FakeChatModel("primary"), _FakeChatModel("fallback"))
    assert llm.reply == "primary"
