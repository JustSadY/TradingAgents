from __future__ import annotations
from enum import Enum
from typing import Optional
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
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])
class TraderProposal(BaseModel):
    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    confidence_score: float = Field(
        default=0.5,
        description="Probability of success for this trade, from 0.0 to 1.0. Critical for Kelly sizing.",
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    take_profit_price: Optional[float] = Field(
        default=None,
        description="Optional target price to take profit.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )
def render_trader_proposal(proposal: TraderProposal) -> str:
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
        f"**Confidence Score**: {proposal.confidence_score:.2f}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.take_profit_price is not None:
        parts.extend(["", f"**Take Profit**: {proposal.take_profit_price}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
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
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
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
    review_report: str = ""
    investment_plan: str = ""
    trader_plan: str = ""
    final_decision: str = ""
    @classmethod
    def from_state(cls, state: dict, signal: str) -> "PropagateResult":
        from backend.trading_agents.agents.utils.agent_states import StateKeys
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
            review_report=state.get(StateKeys.REVIEW_REPORT, ""),
            investment_plan=state.get(StateKeys.INVESTMENT_PLAN, ""),
            trader_plan=state.get(StateKeys.TRADER_INVESTMENT_PLAN, ""),
            final_decision=state.get(StateKeys.FINAL_TRADE_DECISION, ""),
        )
