"""Rebalance sizing is computed, never taken from a model."""

from __future__ import annotations

from decimal import Decimal

from backend.services import portfolio_rebalance_service as svc
from backend.services.portfolio_rebalance_planner import (
    MAX_POSITION_PCT,
    MIN_TRADE_NOTIONAL,
    build_plan,
    health_score,
    plan_trades,
    portfolio_issues,
)


def _portfolio(holdings: list[dict], cash: float, total: float) -> dict:
    return {"holdings": holdings, "cash_available": cash, "total_value": total}


def _holding(ticker: str, market_value: float, price: float, quantity: float, side: str = "long") -> dict:
    return {
        "ticker": ticker,
        "market_value": market_value,
        "current_price": price,
        "quantity": quantity,
        "side": side,
    }


def test_over_concentrated_long_is_trimmed_to_the_limit():
    holdings = [_holding("AAPL", 600, 100, 6)]
    trades = plan_trades(holdings, Decimal("1000"), Decimal("100"))

    assert len(trades) == 1
    # 60% of 1000 is 600; the 25% cap is 250, so 350 of notional must go.
    assert trades[0]["action"] == "SELL"
    assert trades[0]["quantity"] == 3.5
    assert trades[0]["notional"] == 350.0


def test_a_short_position_is_reduced_by_buying():
    holdings = [_holding("TSLA", 600, 100, 6, side="short")]
    trades = plan_trades(holdings, Decimal("1000"), Decimal("100"))

    assert trades[0]["action"] == "BUY"


def test_reduction_never_exceeds_the_quantity_held():
    """A stale or wrong market value must not produce a sell larger than the position.

    Raw arithmetic here wants (900 - 250) / 100 = 6.5 shares, but only 2 are
    held. The clamped trade is still $200, well above the dust threshold, so
    this measures the clamp rather than the dust filter.
    """
    holdings = [_holding("NVDA", 900, 100, 2)]
    trades = plan_trades(holdings, Decimal("1000"), Decimal("100"))

    assert trades[0]["quantity"] == 2


def test_dust_trades_are_dropped():
    """Below the minimum notional, commission and slippage dominate."""
    total = Decimal("1000")
    # 25.1% of 1000 is 251 -> only $1 over the cap.
    holdings = [_holding("MSFT", 251, 100, 2.51)]
    trades = plan_trades(holdings, total, Decimal("100"))

    assert trades == []
    assert MIN_TRADE_NOTIONAL > Decimal("1")


def test_positions_within_policy_produce_no_trades():
    holdings = [_holding("AAPL", 200, 100, 2), _holding("MSFT", 200, 100, 2)]
    assert plan_trades(holdings, Decimal("1000"), Decimal("600")) == []


def test_issues_and_score_agree_with_each_other():
    holdings = [_holding("AAPL", 600, 100, 6)]
    total, cash = Decimal("1000"), Decimal("10")

    issues = portfolio_issues(holdings, total, cash)
    assert any("AAPL" in i for i in issues)
    assert any("Cash" in i for i in issues)
    # Concentration and a thin cash reserve both cost points.
    assert health_score(holdings, total, cash) < 100


def test_healthy_portfolio_scores_full_marks():
    holdings = [_holding("AAPL", 200, 100, 2), _holding("MSFT", 200, 100, 2)]
    total, cash = Decimal("1000"), Decimal("100")

    assert portfolio_issues(holdings, total, cash) == []
    assert health_score(holdings, total, cash) == 100
    assert MAX_POSITION_PCT == Decimal("25")


async def test_model_prose_cannot_change_any_number(monkeypatch):
    """The merge step accepts explanations and nothing else.

    A model that returns its own trades, quantities or score must not be able
    to place them in front of the user.
    """
    plan = build_plan(_portfolio([_holding("AAPL", 600, 100, 6)], cash=100, total=1000))
    hostile = {
        "summary": "looks fine",
        "rationales": ["trimming concentration"],
        # Everything below is ignored.
        "score": 100,
        "issues": [],
        "suggestions": [{"action": "BUY", "ticker": "SCAM", "quantity": 9999}],
    }

    merged = svc._merge(plan, hostile)

    assert merged["score"] == plan["score"]
    assert merged["issues"] == plan["issues"]
    assert [s["ticker"] for s in merged["suggestions"]] == ["AAPL"]
    assert merged["suggestions"][0]["action"] == "SELL"
    assert merged["suggestions"][0]["quantity"] == plan["suggestions"][0]["quantity"]


def test_missing_rationales_do_not_shift_onto_the_wrong_trade():
    plan = build_plan(
        _portfolio(
            [_holding("AAPL", 600, 100, 6), _holding("MSFT", 300, 100, 3)],
            cash=100,
            total=1000,
        )
    )
    assert len(plan["suggestions"]) == 2

    merged = svc._merge(plan, {"summary": "s", "rationales": ["only one"]})

    assert merged["suggestions"][0]["rationale"] == "only one"
    assert merged["suggestions"][1]["rationale"] == ""


def test_summary_is_derived_when_the_model_returns_nothing():
    """A model outage costs the explanation, not the numbers."""
    plan = build_plan(_portfolio([_holding("AAPL", 600, 100, 6)], cash=100, total=1000))

    merged = svc._merge(plan, svc._NO_NARRATIVE)

    assert merged["summary"]
    assert merged["suggestions"] == [
        {
            "action": "SELL",
            "ticker": "AAPL",
            "quantity": plan["suggestions"][0]["quantity"],
            "rationale": "",
            "urgency": plan["suggestions"][0]["urgency"],
        }
    ]
