"""Tests for the prompt token-budget helpers (report truncation + history tail)."""

from backend.trading_agents.agents.runtime.report_aggregator import (
    _truncate_report,
    build_resources,
    tail_history,
)


def test_truncate_report_keeps_short_reports_intact():
    assert _truncate_report("short text", 6000) == "short text"


def test_truncate_report_caps_long_reports():
    out = _truncate_report("X" * 20000, 6000)
    assert len(out) < 6200  # cap + the truncation marker
    assert "truncated" in out


def test_build_resources_caps_each_report():
    state = {"market_report": "M" * 20000, "news_report": "brief news"}
    fields = {"market_report": "Market", "news_report": "News"}
    out = build_resources(state, fields, max_chars_per_report=4000)
    assert "Market:" in out and "News:" in out
    assert "brief news" in out  # short report untouched
    assert "truncated" in out  # long report cut


def test_build_resources_skips_empty_reports():
    state = {"market_report": "data", "news_report": "   "}
    fields = {"market_report": "Market", "news_report": "News"}
    out = build_resources(state, fields, max_chars_per_report=0)
    assert "Market:" in out
    assert "News:" not in out


def test_tail_history_keeps_recent_tail():
    history = "\n".join(f"turn {i}: " + "z" * 500 for i in range(50))
    out = tail_history(history, 4000)
    assert len(out) < len(history)
    assert "omitted" in out
    # The most recent turn must survive.
    assert "turn 49" in out


def test_tail_history_noop_when_short():
    assert tail_history("only one turn", 4000) == "only one turn"
