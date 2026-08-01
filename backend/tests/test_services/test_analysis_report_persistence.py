"""Regression tests for report handling between graph output and persistence."""

from __future__ import annotations


def test_selected_active_empty_report_becomes_visible_degraded_fallback(monkeypatch):
    from backend.services.analysis import reports

    monkeypatch.setattr(
        "backend.trading_agents.agents.analyst_registry.report_key_for",
        lambda analyst: {"market": "market_report", "social": "sentiment_report"}.get(analyst),
    )
    monkeypatch.setattr(
        "backend.trading_agents.agents.analyst_registry.get_report_fields",
        lambda: {"market_report": "Market Analyst", "sentiment_report": "Sentiment Analyst"},
    )

    values = reports.normalise_selected_analyst_reports(
        {
            "market_report": [{"type": "text", "text": "Technical evidence is available."}],
            "sentiment_report": " \n ",
        },
        ["market", "social"],
        is_enabled=lambda _key: True,
    )

    assert values["market_report"] == "Technical evidence is available."
    assert values["sentiment_report"].startswith("⚠️ Sentiment Analyst report unavailable:")


def test_disabled_selected_analyst_is_not_misrepresented_as_a_failed_report(monkeypatch):
    from backend.services.analysis import reports

    monkeypatch.setattr(
        "backend.trading_agents.agents.analyst_registry.report_key_for",
        lambda analyst: {"market": "market_report", "social": "sentiment_report"}.get(analyst),
    )

    values = reports.normalise_selected_analyst_reports(
        {"market_report": "Market evidence"},
        ["market", "social"],
        is_enabled=lambda key: key == "market",
    )

    assert values == {"market_report": "Market evidence"}


def test_terminal_report_values_normalise_content_and_do_not_overwrite_saved_text_with_blank(monkeypatch):
    from backend.services.analysis import reports

    monkeypatch.setattr(
        reports,
        "analysis_result_report_columns",
        lambda: frozenset({"market_report", "final_decision", "agent_qa_report"}),
    )

    values = reports.terminal_report_column_values(
        {
            "agent_qa_report": [{"type": "text", "text": "Cross-check complete."}],
            "final_trade_decision": " \n ",
        },
        {"market_report": "Persist this report", "sentiment_report": "No column for this report"},
    )

    assert values == {
        "market_report": "Persist this report",
        "agent_qa_report": "Cross-check complete.",
    }
    assert "final_decision" not in values
    assert "sentiment_report" not in values


def test_stream_alias_maps_graph_final_trade_decision_to_real_model_column():
    from backend.services.analysis.reports import persistence_column_for_report

    assert persistence_column_for_report("final_trade_decision") == "final_decision"
    assert persistence_column_for_report("market_report") == "market_report"


def test_runtime_stream_fields_follow_live_registry(monkeypatch):
    from backend.services.analysis import reports

    monkeypatch.setattr(reports, "registered_analyst_report_fields", lambda: ("market_report", "plugin_report"))

    fields = reports.report_stream_fields()

    assert "market_report" in fields
    assert "plugin_report" in fields
    assert "agent_qa_report" in fields
    assert "final_trade_decision" in fields
