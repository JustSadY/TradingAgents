from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.services.performance_service import (
    _regime_aware_weight_rows,
    get_analyst_performance_context,
)


def _row(
    *,
    ticker: str,
    trade_date: str,
    market_rating: str,
    fundamentals_rating: str,
    raw_return: float,
    regime: dict[str, str],
):
    return SimpleNamespace(
        ticker=ticker,
        trade_date=trade_date,
        market_report=f"Rating: {market_rating}",
        fundamentals_report=f"Rating: {fundamentals_rating}",
        raw_return=raw_return,
        market_regime_json=regime,
    )


def test_regime_aware_weights_shrink_sparse_ticker_and_regime_samples():
    rows = [
        _row(
            ticker="NVDA",
            trade_date="2026-08-01",
            market_rating="Buy",
            fundamentals_rating="Sell",
            raw_return=0.04,
            regime={"trend": "bull", "risk": "risk_on", "volatility": "elevated", "macro": "late_expansion"},
        ),
        _row(
            ticker="MSFT",
            trade_date="2026-07-20",
            market_rating="Buy",
            fundamentals_rating="Buy",
            raw_return=0.02,
            regime={"trend": "bull", "risk": "risk_on", "volatility": "normal", "macro": "late_expansion"},
        ),
        _row(
            ticker="AAPL",
            trade_date="2026-04-01",
            market_rating="Sell",
            fundamentals_rating="Buy",
            raw_return=-0.03,
            regime={"trend": "bear", "risk": "risk_off", "volatility": "high", "macro": "contraction"},
        ),
    ]

    weights = _regime_aware_weight_rows(
        rows,
        ticker="NVDA",
        current_regime={"trend": "bull", "risk": "risk_on", "volatility": "elevated", "macro": "late_expansion"},
        report_fields={"market_report": "Market", "fundamentals_report": "Fundamentals"},
        now=datetime(2026, 8, 8, tzinfo=UTC),
    )
    market = next(item for item in weights if item["key"] == "market")
    fundamentals = next(item for item in weights if item["key"] == "fundamentals")

    assert market["ticker_samples"] == 1
    assert market["regime_samples"] == 2
    # A tiny correct NVDA slice must be shrunk well below an unearned 100%.
    assert market["ticker_accuracy"] < 100.0
    assert market["regime_accuracy"] < 100.0
    assert market["effective_accuracy"] > fundamentals["effective_accuracy"]
    assert sum(item["effective_weight"] for item in weights) == pytest.approx(100.0, abs=0.15)


async def test_regime_aware_prompt_context_is_explicit_about_shrinkage(monkeypatch):
    async def fake_stats(_db, *, user_id, ticker, current_regime):
        assert user_id == 7
        assert ticker == "NVDA"
        assert current_regime == {"risk": "risk_on"}
        return {
            "attribution": [
                {
                    "label": "Market",
                    "effective_accuracy": 63.2,
                    "effective_weight": 54.0,
                    "global_accuracy": 61.0,
                    "global_samples": 30,
                    "ticker_accuracy": 68.0,
                    "ticker_samples": 5,
                    "regime_accuracy": 70.0,
                    "regime_samples": 4,
                    "recent_accuracy": 65.0,
                    "recent_samples": 7,
                }
            ]
        }

    monkeypatch.setattr(
        "backend.services.performance_service.get_regime_aware_analyst_attribution_stats",
        fake_stats,
    )

    context = await get_analyst_performance_context(
        object(),
        user_id=7,
        ticker="NVDA",
        current_regime={"risk": "risk_on"},
        regime_aware=True,
    )

    assert "REGIME-AWARE" in context
    assert "beta-binomial shrinkage" in context
    assert "Market: Effective Accuracy = 63.2%" in context
