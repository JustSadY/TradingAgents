from typing import Annotated, Any

from langgraph.graph import MessagesState
from typing_extensions import TypedDict


class StateKeys:
    COMPANY = "company_of_interest"
    ASSET_TYPE = "asset_type"
    TRADE_DATE = "trade_date"
    SENDER = "sender"
    PAST_CONTEXT = "past_context"
    MARKET_REPORT = "market_report"
    SENTIMENT_REPORT = "sentiment_report"
    NEWS_REPORT = "news_report"
    FUNDAMENTALS_REPORT = "fundamentals_report"
    MACRO_REPORT = "macro_report"
    OPTIONS_REPORT = "options_report"
    QUANT_REPORT = "quant_report"
    EARNINGS_REPORT = "earnings_report"
    INSIDER_REPORT = "insider_report"
    OWNERSHIP_REPORT = "ownership_report"
    RATINGS_REPORT = "ratings_report"
    SHORT_INTEREST_REPORT = "short_interest_report"
    VALUATION_REPORT = "valuation_report"
    CATALYST_REPORT = "catalyst_report"
    REVIEW_REPORT = "review_report"
    SYNTHESIS_REPORT = "synthesis_report"
    AUDIT_REPORT = "audit_report"
    AGENT_QA_REPORT = "agent_qa_report"
    INVESTMENT_DEBATE_STATE = "investment_debate_state"
    INVESTMENT_PLAN = "investment_plan"
    RISK_DEBATE_STATE = "risk_debate_state"
    STRATEGY_CONTEXT = "strategy_context"
    ANALYSIS_PLAN_JSON = "analysis_plan_json"
    ANALYSIS_PLAN_REPORT = "analysis_plan_report"
    SYNTHESIS_JSON = "synthesis_json"
    MARKET_REGIME_JSON = "market_regime_json"
    STRATEGY_CANDIDATE_JSON = "strategy_candidate_json"
    STRATEGY_RECONCILIATION_REPORT = "strategy_reconciliation_report"
    PM_PROPOSAL_JSON = "pm_proposal_json"
    PM_PROPOSAL_REPORT = "pm_proposal_report"
    PORTFOLIO_DECISION_JSON = "portfolio_decision_json"
    DECISION_TRANSITION_JSON = "decision_transition_json"
    CALIBRATED_CONFIDENCE = "calibrated_confidence"
    ANALYSIS_MODE = "analysis_mode"
    LEARNING_ELIGIBLE = "learning_eligible"
    HARD_RISK_EXIT = "hard_risk_exit"
    FINAL_TRADE_DECISION = "final_trade_decision"
    ALL_REPORT_KEYS: tuple[str, ...] = (
        MARKET_REPORT,
        SENTIMENT_REPORT,
        NEWS_REPORT,
        FUNDAMENTALS_REPORT,
        MACRO_REPORT,
        OPTIONS_REPORT,
        QUANT_REPORT,
        EARNINGS_REPORT,
        INSIDER_REPORT,
        OWNERSHIP_REPORT,
        RATINGS_REPORT,
        SHORT_INTEREST_REPORT,
        VALUATION_REPORT,
        CATALYST_REPORT,
        REVIEW_REPORT,
        SYNTHESIS_REPORT,
        AUDIT_REPORT,
        AGENT_QA_REPORT,
        ANALYSIS_PLAN_REPORT,
        INVESTMENT_PLAN,
        STRATEGY_RECONCILIATION_REPORT,
        PM_PROPOSAL_REPORT,
        FINAL_TRADE_DECISION,
    )

class InvestDebateState(TypedDict):
    bull_history: Annotated[str, "Bullish Conversation history"]
    bear_history: Annotated[str, "Bearish Conversation history"]
    history: Annotated[str, "Conversation history"]
    current_response: Annotated[str, "Latest response"]
    judge_decision: Annotated[str, "Final judge decision"]
    count: Annotated[int, "Length of the current conversation"]

class RiskDebateState(TypedDict):
    aggressive_history: Annotated[str, "Aggressive Agent's Conversation history"]
    conservative_history: Annotated[str, "Conservative Agent's Conversation history"]
    neutral_history: Annotated[str, "Neutral Agent's Conversation history"]
    history: Annotated[str, "Conversation history"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[str, "Latest response by the aggressive analyst"]
    current_conservative_response: Annotated[str, "Latest response by the conservative analyst"]
    current_neutral_response: Annotated[str, "Latest response by the neutral analyst"]
    judge_decision: Annotated[str, "Judge's decision"]
    count: Annotated[int, "Length of the current conversation"]

class AgentState(MessagesState):
    company_of_interest: Annotated[str, "Company that we are interested in trading"]
    asset_type: Annotated[str, "Asset type under analysis such as stock or crypto"]
    trade_date: Annotated[str, "What date we are trading at"]
    sender: Annotated[str, "Agent that sent this message"]
    market_report: Annotated[str, "Report from the Market Analyst"]
    sentiment_report: Annotated[str, "Report from the Sentiment Analyst"]
    news_report: Annotated[str, "Report from the News Researcher of current world affairs"]
    fundamentals_report: Annotated[str, "Report from the Fundamentals Researcher"]
    macro_report: Annotated[str, "Report from the Macro Analyst"]
    options_report: Annotated[str, "Report from the Options Analyst"]
    quant_report: Annotated[str, "Report from the Quant Analyst"]
    earnings_report: Annotated[str, "Report from the Earnings Analyst"]
    insider_report: Annotated[str, "Report from the Insider Activity Analyst"]
    ownership_report: Annotated[str, "Report from the Institutional Ownership Analyst"]
    ratings_report: Annotated[str, "Report from the Analyst Ratings Analyst (Wall Street consensus)"]
    short_interest_report: Annotated[str, "Report from the Short Interest Analyst (squeeze positioning)"]
    valuation_report: Annotated[str, "Report from the Valuation Analyst (relative valuation vs sector)"]
    catalyst_report: Annotated[str, "Report from the Catalyst Calendar Analyst"]
    review_report: Annotated[str, "Report from the Performance Review Analyst"]
    synthesis_report: Annotated[str, "Report identifying alignments and conflicts between analyst reports"]
    audit_report: Annotated[str, "Real-time audit report checking for hallucinations and reasoning gaps"]
    agent_qa_report: Annotated[str, "Cross-examination Q&A between analysts after they finish their reports"]
    strategy_context: Annotated[
        dict[str, Any],
        "Preloaded exact strategy snapshot plus planner-safe blind context; graph nodes never open a DB session.",
    ]
    analysis_plan_json: Annotated[dict[str, Any], "Neutral pre-analysis investigation plan"]
    analysis_plan_report: Annotated[str, "Human-readable neutral analysis plan"]
    synthesis_json: Annotated[dict[str, Any], "Structured synthesis evidence/conflict assessment"]
    market_regime_json: Annotated[dict[str, Any], "Structured market-regime snapshot"]
    strategy_candidate_json: Annotated[dict[str, Any], "Non-persisted proposed AssetStrategy revision"]
    strategy_reconciliation_report: Annotated[str, "Human-readable strategy reconciliation"]
    pm_proposal_json: Annotated[dict[str, Any], "Raw non-executable Portfolio Manager proposal"]
    pm_proposal_report: Annotated[str, "Human-readable raw Portfolio Manager proposal"]
    investment_debate_state: Annotated[InvestDebateState, "Current state of the debate on if to invest or not"]
    investment_plan: Annotated[str, "Plan generated by the Analyst"]
    risk_debate_state: Annotated[RiskDebateState, "Current state of the debate on evaluating risk"]
    portfolio_decision_json: Annotated[
        dict[str, Any] | str,
        "Canonical accepted PortfolioDecision emitted by the Decision Stability Controller",
    ]
    decision_transition_json: Annotated[dict[str, Any], "Auditable PM proposal-to-accepted decision transition"]
    calibrated_confidence: Annotated[float | None, "Statistically calibrated controller confidence"]
    analysis_mode: Annotated[str, "live, historical, or time_travel"]
    learning_eligible: Annotated[bool, "Whether this run may update strategy/memory/performance learning"]
    hard_risk_exit: Annotated[
        dict[str, Any] | None,
        "Explicit stop/drawdown/portfolio breach input that bypasses hysteresis with reduce-only execution",
    ]
    final_trade_decision: Annotated[str, "Accepted final decision after deterministic stability control"]
    final_signal: Annotated[
        str,
        "Structured final rating (Buy/Overweight/Hold/Underweight/Sell) carried straight "
        "from the Portfolio Manager's PortfolioDecision, bypassing markdown re-parsing.",
    ]
    past_context: Annotated[
        str, "Ambient run context injected at run start (performance attribution, market pulse, scenarios)"
    ]
