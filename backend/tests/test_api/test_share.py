"""Public share-report API contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.api import share as share_api


async def test_shared_report_exposes_only_canonical_report_fields(monkeypatch) -> None:
    report_text_fields = (
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "macro_report",
        "options_report",
        "quant_report",
        "earnings_report",
        "insider_report",
        "ownership_report",
        "ratings_report",
        "short_interest_report",
        "valuation_report",
        "catalyst_report",
        "review_report",
        "synthesis_report",
        "audit_report",
        "agent_qa_report",
        "investment_plan",
        "trader_plan",
        "final_decision",
        "judge_decision",
        "trader_proposal_json",
        "llm_provider",
        "llm_model",
    )
    analysis = SimpleNamespace(
        ticker="AAPL",
        trade_date="2026-07-29",
        signal="Hold",
        status="completed",
        **dict.fromkeys(report_text_fields, ""),
        bull_history=None,
        bear_history=None,
        investment_debate_history=None,
        risk_debate_history=None,
        chart_annotations={
            "portfolio_decision": {
                "rating": "Buy",
                "position_size_pct": 5,
                "stop_loss": 95,
            }
        },
        risk_metrics=None,
        quality=None,
        degraded=False,
        failed_agents=None,
        duration_seconds=0.0,
    )
    analysis.fundamentals_report = "Canonical fundamentals"
    analysis.investment_plan = "Canonical investment plan"
    analysis.market_report = "Canonical market analysis"
    analysis.risk_debate_history = ["Aggressive Analyst: Keep the position small"]
    now = datetime.now(UTC)
    shared = SimpleNamespace(analysis_id=123, expires_at=now + timedelta(hours=1), created_at=now)

    async def get_shared_report(_db, _token):
        return shared

    async def get_analysis_for_share(_db, analysis_id):
        assert analysis_id == 123
        return analysis

    monkeypatch.setattr(share_api.share_service, "get_shared_report", get_shared_report)
    monkeypatch.setattr(share_api.share_service, "get_analysis_for_share", get_analysis_for_share)

    payload = await share_api.get_shared_report("share-token", object())

    # A public link is deliberately a read-only view, but it must still carry
    # every analysis report that the public frontend can render.  The previous
    # UI bug was particularly easy to miss because the backend already sent
    # this data while rendering only three decision sections.
    for field in report_text_fields:
        assert field in payload

    assert payload["market_report"] == "Canonical market analysis"
    assert payload["fundamentals_report"] == "Canonical fundamentals"
    assert payload["investment_plan"] == "Canonical investment plan"
    assert payload["risk_debate_history"] == ["Aggressive Analyst: Keep the position small"]
    assert payload["portfolio_decision"] == {
        "rating": "Buy",
        "position_size_pct": 5,
        "stop_loss": 95,
    }
    assert "fundamental_report" not in payload
    assert "research_report" not in payload
