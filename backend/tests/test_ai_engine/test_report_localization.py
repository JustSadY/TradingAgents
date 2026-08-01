from __future__ import annotations

import pandas as pd

from backend.trading_agents.agents.data.chart_tools import _algorithmic_pattern_detection
from backend.trading_agents.agents.runtime.report_aggregator import extract_executive_summary
from backend.trading_agents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchBias,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    render_pm_decision,
    render_research_plan,
    render_trader_proposal,
)
from backend.trading_agents.graph.reflection import Reflector


def test_structured_renderers_localize_turkish_scaffolding_and_actions():
    plan = render_research_plan(
        ResearchPlan(
            research_bias=ResearchBias.BULLISH,
            rationale="Kanıtlar olumlu.",
            key_evidence="Büyüme ve talep verileri olumlu.",
            risk_conditions="Beklenenden zayıf kılavuzluk bu görüşü geçersiz kılar.",
        ),
        "Turkish",
    )
    trader = render_trader_proposal(
        TraderProposal(
            action=TraderAction.SELL,
            reasoning="Risk seviyesi yükseldi.",
            confidence_score=0.71,
            entry_price=100.0,
            stop_loss=105.0,
            take_profit_price=92.0,
        ),
        "Turkish",
    )
    decision = render_pm_decision(
        PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            executive_summary="Yükseliş senaryosu baskın.",
            investment_thesis="Büyüme ve talep görünümü güçlü.",
        ),
        "Turkish",
    )

    assert "**Araştırma Eğilimi**: Olumlu" in plan
    assert "**İşlem**: Sat" in trader
    assert "**Nihai İşlem Önerisi**: **Sat**" in trader
    assert "**Derecelendirme**: Ağırlığı Artır" in decision
    assert "Recommendation" not in plan
    assert "FINAL TRANSACTION PROPOSAL" not in trader
    assert "Executive Summary" not in decision


def test_summary_extraction_understands_turkish_heading_without_cutting_bold_metrics():
    report = """1. **Yönetici Özeti:**
- Trend olumlu.
- **Güven:** yüksek.

2. **Detaylı Analiz:**
Bu bölüm özet promptuna girmemelidir.
"""

    assert extract_executive_summary(report) == "- Trend olumlu.\n- **Güven:** yüksek."


def test_algorithmic_chart_fallback_uses_configured_output_language(monkeypatch):
    from backend.trading_agents.dataflows import config

    monkeypatch.setattr(config, "get_config", lambda: {"output_language": "Turkish"})
    chart = pd.DataFrame(
        {
            "High": [101.0, 102.0, 103.0, 104.0, 105.0] * 7,
            "Low": [99.0, 98.0, 97.0, 96.0, 95.0] * 7,
            "Close": [100.0, 100.0, 101.0, 102.0, 103.0] * 7,
        }
    )

    rendered = _algorithmic_pattern_detection(chart, "NVDA")

    assert "Algoritmik Grafik Formasyonu Analizi" in rendered
    assert "Tespit Edilen Formasyon" in rendered
    assert "Çizilen Destek Seviyeleri" in rendered
    assert "Detected Pattern" not in rendered


def test_reflector_uses_the_shared_strict_language_block(monkeypatch):
    from backend.trading_agents.dataflows import config

    monkeypatch.setattr(config, "get_config", lambda: {"output_language": "Turkish"})

    class FakeLLM:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return type("Result", (), {"content": "Kısa değerlendirme."})()

    llm = FakeLLM()
    result = Reflector(llm).reflect_on_final_decision("Hold", 0.1, 0.02)

    assert result == "Kısa değerlendirme."
    assert "CRITICAL LANGUAGE REQUIREMENT" in llm.messages[0][1]
    assert "Turkish" in llm.messages[0][1]
