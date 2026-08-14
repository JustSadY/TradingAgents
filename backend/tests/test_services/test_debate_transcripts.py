"""Regression tests for debate transcript formatting and Risk Debate parsing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.trading_agents.agents.runtime.debate_history import debate_messages, format_debate_argument


def test_debate_messages_keep_multiline_markdown_in_one_speaker_turn():
    history = (
        "Bull Analyst: **Catalyst:** Earnings improved.\n"
        "- Revenue growth accelerated\n"
        "- Margins expanded\n"
        "Bear Analyst: Valuation still prices in execution perfection."
    )

    assert debate_messages(history) == [
        {
            "sender": "Bull Analyst",
            "content": "**Catalyst:** Earnings improved.\n- Revenue growth accelerated\n- Margins expanded",
        },
        {"sender": "Bear Analyst", "content": "Valuation still prices in execution perfection."},
    ]

def test_debate_argument_strips_repeated_provider_role_heading():
    argument = format_debate_argument(
        "Aggressive Analyst",
        SimpleNamespace(content="**Aggressive Risk Analyst**\n**Upside:** Momentum is improving."),
    )

    assert argument == "Aggressive Analyst: **Upside:** Momentum is improving."

def test_debate_argument_strips_dangling_markdown_delimiter_before_response():
    argument = format_debate_argument(
        "Aggressive Analyst",
        "**\nThe upside case remains well supported by earnings growth.",
    )

    assert argument == "Aggressive Analyst: The upside case remains well supported by earnings growth."

def test_debate_messages_accept_legacy_markdown_headings():
    history = "### Aggressive Risk Analyst\n**Upside:** Breakout volume supports upside."

    assert debate_messages(history) == [
        {"sender": "Aggressive Analyst", "content": "**Upside:** Breakout volume supports upside."}
    ]

def test_risk_parser_accepts_markdown_role_headings():
    from backend.trading_agents.agents.main.risk import _parse_perspectives

    response = """**Aggressive Risk Analyst**
**Upside:** Momentum supports the high-reward case.

### Conservative Risk Analyst
**Risk:** A defined stop is necessary before adding exposure.

NEUTRAL:
Use a smaller initial position and reassess after earnings."""

    assert _parse_perspectives(response) == {
        "aggressive": "**Upside:** Momentum supports the high-reward case.",
        "conservative": "**Risk:** A defined stop is necessary before adding exposure.",
        "neutral": "Use a smaller initial position and reassess after earnings.",
    }

@pytest.mark.asyncio
async def test_merged_risk_debate_preserves_all_perspectives_and_language_settings(monkeypatch):
    from backend.trading_agents.agents.main import risk

    class _LLM:
        def __init__(self):
            self.prompt = ""

        async def ainvoke(self, prompt):
            self.prompt = prompt
            return SimpleNamespace(
                content=[
                    {"type": "text", "text": "AGGRESSIVE:\n**Upside:** Momentum supports a measured add."},
                    {"type": "text", "text": "CONSERVATIVE:\n**Risk:** Keep a hard stop below support."},
                    {"type": "text", "text": "NEUTRAL:\nStage the entry and cap downside."},
                ]
            )

    llm = _LLM()
    ctx = SimpleNamespace(
        is_enabled=lambda key: key == "risk_debate",
        llm_for=lambda _key: llm,
    )
    monkeypatch.setattr(risk, "get_general_settings_block", lambda: "\nLANGUAGE: Turkish only.")
    monkeypatch.setattr(risk, "get_system_instruction_override", lambda _key: "Use concise risk controls.")

    result = await risk.create_risk_debate_node(ctx)(
        {
            "investment_plan": "Research posture: Bullish; earnings quality improved.",
            "market_report": "## Executive Summary\nTrend remains constructive.",
        }
    )

    transcript = result["risk_debate_state"]
    assert transcript["count"] == 3
    assert transcript["history"] == (
        "Aggressive Analyst: **Upside:** Momentum supports a measured add.\n"
        "Conservative Analyst: **Risk:** Keep a hard stop below support.\n"
        "Neutral Analyst: Stage the entry and cap downside."
    )
    assert "LANGUAGE: Turkish only." in llm.prompt
    assert "Use concise risk controls." in llm.prompt
    assert "TRADER'S INVESTMENT PLAN" not in llm.prompt
    assert "RESEARCH MANAGER EVIDENCE BRIEF" in llm.prompt
