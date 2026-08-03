from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from backend.trading_agents.agents.utils.report_localization import report_bias, report_rating, report_texts

class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"

class ResearchBias(str, Enum):
    """Non-executable research posture used by upstream research agents.

    This deliberately does not reuse :class:`PortfolioRating`.  Research and
    risk agents are evidence producers, while the Portfolio Manager is the
    only component allowed to produce a Buy/Sell/Hold-style decision.
    """

    BULLISH = "Bullish"
    NEUTRAL = "Neutral"
    BEARISH = "Bearish"

class ResearchPlan(BaseModel):
    research_bias: ResearchBias = Field(
        description=(
            "The evidence posture only. Exactly one of Bullish / Neutral / Bearish. "
            "This is not a trading instruction; do not use Buy, Sell, Hold, "
            "Overweight, Underweight, quantities, or position sizes."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments support the evidence posture. "
            "Speak naturally, as if to a teammate."
        ),
    )
    key_evidence: str = Field(
        description=(
            "The most decision-relevant, source-grounded evidence, including "
            "what would invalidate it. Do not prescribe an order direction or size."
        ),
    )
    risk_conditions: str = Field(
        description=(
            "Open questions, invalidation conditions, and risk checks for the "
            "Portfolio Manager. Do not prescribe an order direction, entry, stop, "
            "target, leverage, or quantity."
        ),
    )

def render_research_plan(plan: ResearchPlan, output_language: str | None = None) -> str:
    labels = report_texts(("research_bias", "rationale", "key_evidence", "risk_conditions"), output_language)
    return "\n".join(
        [
            f"**{labels['research_bias']}**: {report_bias(plan.research_bias.value, output_language)}",
            "",
            f"**{labels['rationale']}**: {plan.rationale}",
            "",
            f"**{labels['key_evidence']}**: {plan.key_evidence}",
            "",
            f"**{labels['risk_conditions']}**: {plan.risk_conditions}",
        ]
    )

class PortfolioDecision(BaseModel):
    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "The Portfolio Manager's calibrated probability of a favourable outcome, "
            "from 0.0 to 1.0. This is the sole execution confidence used by the order "
            "engine; do not copy an upstream agent's score without reassessing it."
        ),
    )
    entry_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Planned entry or execution reference price in the instrument's quote currency. "
            "Required for a new Buy/Overweight entry when a reliable price is available; null for Hold."
        ),
    )
    stop_loss: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Protective stop price in the instrument's quote currency. For a long it must be below entry; "
            "for a short it must be above entry. Null only when no order should be opened."
        ),
    )
    take_profit_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Planned take-profit price in the instrument's quote currency. For a long it must be above entry; "
            "for a short it must be below entry. Null only when no order should be opened."
        ),
    )
    position_size_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Desired total allocation after the action as a percentage of current portfolio equity. "
            "REQUIRED and non-null for Buy, Overweight, and Underweight: the execution engine sizes "
            "the order from this number alone and skips the order entirely when it is null, so "
            "omitting it silently cancels the trade you just recommended. "
            "Use the full intended target weight for Buy/Overweight, a target below the current "
            "weight for Underweight, and 0 for a full exit (Sell). "
            "Null is correct ONLY for Hold, where no order is placed. "
            "This is the sole AI sizing recommendation; the execution engine still applies hard risk caps."
        ),
    )
    suggested_capital: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Approximate order notional in the portfolio's base currency. It must agree with "
            "position_size_pct and available cash; use 0 for no new order."
        ),
    )
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    recommended_leverage: float = Field(
        default=1.0,
        description=(
            "Final per-stock leverage multiplier for this decision, 1.0 (cash) to "
            "10.0. This is the final Portfolio Manager leverage adjusted for the risk "
            "debate outcome and the persona's risk tolerance. Conservative personas "
            "should cap this near 1.0; only use elevated leverage on high-conviction "
            "ratings (Buy) for liquid instruments with a defined stop-loss."
        ),
    )
    liquidation_price: float | None = Field(
        default=None,
        description=(
            "Optional approximate price at which a leveraged long would be "
            "force-liquidated, for the user's awareness. Leave null when leverage is 1.0."
        ),
    )
    time_horizon: str | None = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )

def render_pm_decision(decision: PortfolioDecision, output_language: str | None = None) -> str:
    labels = report_texts(
        (
            "rating",
            "executive_summary",
            "investment_thesis",
            "confidence_score",
            "entry_price",
            "stop_loss",
            "take_profit",
            "position_sizing",
            "suggested_capital",
            "price_target",
            "recommended_leverage",
            "liquidation_price",
            "time_horizon",
        ),
        output_language,
    )
    parts = [
        f"**{labels['rating']}**: {report_rating(decision.rating.value, output_language)}",
        "",
        f"**{labels['executive_summary']}**: {decision.executive_summary}",
        "",
        f"**{labels['investment_thesis']}**: {decision.investment_thesis}",
        "",
        f"**{labels['confidence_score']}**: {decision.confidence_score:.0%}",
    ]
    if decision.entry_price is not None:
        parts.extend(["", f"**{labels['entry_price']}**: {decision.entry_price}"])
    if decision.stop_loss is not None:
        parts.extend(["", f"**{labels['stop_loss']}**: {decision.stop_loss}"])
    if decision.take_profit_price is not None:
        parts.extend(["", f"**{labels['take_profit']}**: {decision.take_profit_price}"])
    if decision.position_size_pct is not None:
        parts.extend(["", f"**{labels['position_sizing']}**: {decision.position_size_pct:.1f}%"])
    if decision.suggested_capital is not None:
        parts.extend(["", f"**{labels['suggested_capital']}**: {decision.suggested_capital:,.2f}"])
    if decision.price_target is not None:
        parts.extend(["", f"**{labels['price_target']}**: {decision.price_target}"])
    if decision.recommended_leverage and abs(decision.recommended_leverage - 1.0) > 1e-9:
        parts.extend(["", f"**{labels['recommended_leverage']}**: {decision.recommended_leverage:.1f}x"])
    if decision.liquidation_price is not None:
        parts.extend(["", f"**{labels['liquidation_price']}**: {decision.liquidation_price}"])
    if decision.time_horizon:
        parts.extend(["", f"**{labels['time_horizon']}**: {decision.time_horizon}"])
    return "\n".join(parts)

class PropagateResult(BaseModel):
    ticker: str
    trade_date: str
    asset_type: str = "stock"
    signal: str
    market_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    fundamentals_report: str = ""
    macro_report: str = ""
    options_report: str = ""
    quant_report: str = ""
    earnings_report: str = ""
    insider_report: str = ""
    ownership_report: str = ""
    ratings_report: str = ""
    short_interest_report: str = ""
    valuation_report: str = ""
    catalyst_report: str = ""
    review_report: str = ""
    synthesis_report: str = ""
    audit_report: str = ""
    investment_plan: str = ""
    portfolio_decision_json: str = "{}"
    final_decision: str = ""

    @classmethod
    def from_state(cls, state: dict, signal: str) -> PropagateResult:
        from backend.trading_agents.agents.runtime.agent_states import StateKeys

        return cls(
            ticker=state.get(StateKeys.COMPANY, ""),
            trade_date=state.get(StateKeys.TRADE_DATE, ""),
            asset_type=state.get(StateKeys.ASSET_TYPE, "stock"),
            signal=signal,
            market_report=state.get(StateKeys.MARKET_REPORT, ""),
            sentiment_report=state.get(StateKeys.SENTIMENT_REPORT, ""),
            news_report=state.get(StateKeys.NEWS_REPORT, ""),
            fundamentals_report=state.get(StateKeys.FUNDAMENTALS_REPORT, ""),
            macro_report=state.get(StateKeys.MACRO_REPORT, ""),
            options_report=state.get(StateKeys.OPTIONS_REPORT, ""),
            quant_report=state.get(StateKeys.QUANT_REPORT, ""),
            earnings_report=state.get(StateKeys.EARNINGS_REPORT, ""),
            insider_report=state.get(StateKeys.INSIDER_REPORT, ""),
            ownership_report=state.get(StateKeys.OWNERSHIP_REPORT, ""),
            ratings_report=state.get(StateKeys.RATINGS_REPORT, ""),
            short_interest_report=state.get(StateKeys.SHORT_INTEREST_REPORT, ""),
            valuation_report=state.get(StateKeys.VALUATION_REPORT, ""),
            catalyst_report=state.get(StateKeys.CATALYST_REPORT, ""),
            review_report=state.get(StateKeys.REVIEW_REPORT, ""),
            synthesis_report=state.get(StateKeys.SYNTHESIS_REPORT, ""),
            audit_report=state.get(StateKeys.AUDIT_REPORT, ""),
            investment_plan=state.get(StateKeys.INVESTMENT_PLAN, ""),
            portfolio_decision_json=state.get(StateKeys.PORTFOLIO_DECISION_JSON, "{}"),
            final_decision=state.get(StateKeys.FINAL_TRADE_DECISION, ""),
        )
