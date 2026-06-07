"""Tests for the inter-agent cross-examination node (with fake LLMs)."""

from backend.trading_agents.agents.main.agent_qa import _Question, _Questions, create_agent_qa_node
from backend.trading_agents.dataflows.config import set_config


class _FakeStructured:
    def __init__(self, questions):
        self._questions = questions

    async def ainvoke(self, _prompt):
        return _Questions(questions=self._questions)


class _FakeLLM:
    def __init__(self, questions=None, answer="my answer"):
        self._questions = questions or []
        self._answer = answer

    def with_structured_output(self, _schema):
        return _FakeStructured(self._questions)

    async def ainvoke(self, _messages):
        class _R:
            content = self._answer

        return _R()


class _FakeCtx:
    def __init__(self, llm):
        self._llm = llm

    def llm_for(self, _key):
        return self._llm


async def test_qa_produces_transcript_from_two_reports():
    set_config({"agent_qa_enabled": True})
    qs = [_Question(to="Market Analyst", question="Why bullish despite overvaluation?")]
    node = create_agent_qa_node(_FakeCtx(_FakeLLM(questions=qs, answer="Momentum outweighs valuation near-term.")))
    out = await node(
        {
            "company_of_interest": "AAPL",
            "trade_date": "2024-01-01",
            "market_report": "bullish momentum breakout",
            "fundamentals_report": "overvalued on P/E",
        }
    )
    assert "agent_qa_report" in out
    assert "Market Analyst" in out["agent_qa_report"]
    assert "Momentum outweighs" in out["agent_qa_report"]


async def test_qa_skips_with_fewer_than_two_reports():
    set_config({"agent_qa_enabled": True})
    node = create_agent_qa_node(_FakeCtx(_FakeLLM()))
    out = await node({"company_of_interest": "AAPL", "market_report": "only one report"})
    assert out == {}


async def test_qa_disabled_is_noop():
    set_config({"agent_qa_enabled": False})
    node = create_agent_qa_node(_FakeCtx(_FakeLLM(questions=[_Question(to="Market Analyst", question="q")])))
    out = await node({"company_of_interest": "AAPL", "market_report": "a", "fundamentals_report": "b"})
    assert out == {}


async def test_qa_ignores_questions_to_unknown_analyst():
    set_config({"agent_qa_enabled": True})
    qs = [_Question(to="Nonexistent Analyst", question="q")]
    node = create_agent_qa_node(_FakeCtx(_FakeLLM(questions=qs)))
    out = await node({"company_of_interest": "AAPL", "market_report": "a", "fundamentals_report": "b"})
    assert out == {}  # no valid targets -> nothing produced
