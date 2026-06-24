from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class ResearchPlan(BaseModel):
    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    return "\n".join(
        [
            f"**Recommendation**: {plan.recommendation.value}",
            "",
            f"**Rationale**: {plan.rationale}",
            "",
            f"**Strategic Actions**: {plan.strategic_actions}",
        ]
    )


class TraderProposal(BaseModel):
    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and the research plan. Two to four sentences."
        ),
    )
    confidence_score: float = Field(
        default=0.5,
        description="Probability of success for this trade, from 0.0 to 1.0. Critical for Kelly sizing.",
    )
    entry_price: float | None = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: float | None = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    take_profit_price: float | None = Field(
        default=None,
        description="Optional target price to take profit.",
    )
    position_sizing: str | None = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )
    recommended_leverage: float = Field(
        default=1.0,
        description=(
            "Per-stock leverage multiplier for this trade, from 1.0 (no leverage / "
            "cash) up to 10.0. Choose based on conviction AND the instrument's "
            "volatility: use 1.0-2.0 for volatile or speculative names, only raise "
            "leverage for high-confidence setups on liquid, stable instruments with "
            "a well-defined stop-loss. Higher leverage tightens the liquidation "
            "price, so size it against the stop, not just the conviction."
        ),
    )
    kelly_size: float | None = Field(
        default=None,
        description="The calculated Kelly Criterion size (0.0 to 1.0) based on confidence and risk/reward.",
    )
    suggested_capital: float | None = Field(
        default=None,
        description="The actual currency amount to allocate based on Kelly size and portfolio balance.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
        f"**Confidence Score**: {proposal.confidence_score:.2f}",
    ]
    if proposal.kelly_size is not None:
        parts.append(f"**Kelly Criterion Size**: {proposal.kelly_size:.2%}")
    if proposal.suggested_capital is not None:
        parts.append(f"**Suggested Capital Allocation**: ${proposal.suggested_capital:,.2f}")
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.take_profit_price is not None:
        parts.extend(["", f"**Take Profit**: {proposal.take_profit_price}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    if proposal.recommended_leverage and abs(proposal.recommended_leverage - 1.0) > 1e-9:
        parts.extend(["", f"**Recommended Leverage**: {proposal.recommended_leverage:.1f}x"])
    parts.extend(
        [
            "",
            f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
        ]
    )
    return "\n".join(parts)


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
    price_target: float | None = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    recommended_leverage: float = Field(
        default=1.0,
        description=(
            "Final per-stock leverage multiplier for this decision, 1.0 (cash) to "
            "10.0. This is the trader's recommended_leverage adjusted for the risk "
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


def render_pm_decision(decision: PortfolioDecision) -> str:
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.recommended_leverage and abs(decision.recommended_leverage - 1.0) > 1e-9:
        parts.extend(["", f"**Recommended Leverage**: {decision.recommended_leverage:.1f}x"])
    if decision.liquidation_price is not None:
        parts.extend(["", f"**Liquidation Price**: {decision.liquidation_price}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
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
    catalyst_report: str = ""
    review_report: str = ""
    synthesis_report: str = ""
    audit_report: str = ""
    investment_plan: str = ""
    trader_plan: str = ""
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
            catalyst_report=state.get(StateKeys.CATALYST_REPORT, ""),
            review_report=state.get(StateKeys.REVIEW_REPORT, ""),
            synthesis_report=state.get(StateKeys.SYNTHESIS_REPORT, ""),
            audit_report=state.get(StateKeys.AUDIT_REPORT, ""),
            investment_plan=state.get(StateKeys.INVESTMENT_PLAN, ""),
            trader_plan=state.get(StateKeys.TRADER_INVESTMENT_PLAN, ""),
            final_decision=state.get(StateKeys.FINAL_TRADE_DECISION, ""),
        )
