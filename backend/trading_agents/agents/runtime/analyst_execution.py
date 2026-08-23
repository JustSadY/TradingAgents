from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystNodeSpec:
    key: str
    agent_node: str
    clear_node: str
    tool_node: str
    report_key: str


@dataclass(frozen=True)
class AnalystExecutionPlan:
    specs: list[AnalystNodeSpec]
    concurrency_limit: int


ANALYST_NODE_SPECS: dict[str, AnalystNodeSpec] = {
    "market": AnalystNodeSpec(
        key="market",
        agent_node="Market Analyst",
        clear_node="Msg Clear Market",
        tool_node="tools_market",
        report_key="market_report",
    ),
    "social": AnalystNodeSpec(
        key="social",
        agent_node="Sentiment Analyst",
        clear_node="Msg Clear Sentiment",
        tool_node="tools_social",
        report_key="sentiment_report",
    ),
    "news": AnalystNodeSpec(
        key="news",
        agent_node="News Analyst",
        clear_node="Msg Clear News",
        tool_node="tools_news",
        report_key="news_report",
    ),
    "fundamentals": AnalystNodeSpec(
        key="fundamentals",
        agent_node="Fundamentals Analyst",
        clear_node="Msg Clear Fundamentals",
        tool_node="tools_fundamentals",
        report_key="fundamentals_report",
    ),
    "macro": AnalystNodeSpec(
        key="macro",
        agent_node="Macro Analyst",
        clear_node="Msg Clear Macro",
        tool_node="tools_macro",
        report_key="macro_report",
    ),
    "options": AnalystNodeSpec(
        key="options",
        agent_node="Options Analyst",
        clear_node="Msg Clear Options",
        tool_node="tools_options",
        report_key="options_report",
    ),
    "quant": AnalystNodeSpec(
        key="quant",
        agent_node="Quant Analyst",
        clear_node="Msg Clear Quant",
        tool_node="tools_quant",
        report_key="quant_report",
    ),
    "earnings": AnalystNodeSpec(
        key="earnings",
        agent_node="Earnings Analyst",
        clear_node="Msg Clear Earnings",
        tool_node="tools_earnings",
        report_key="earnings_report",
    ),
    "insider": AnalystNodeSpec(
        key="insider",
        agent_node="Insider Activity Analyst",
        clear_node="Msg Clear Insider",
        tool_node="tools_insider",
        report_key="insider_report",
    ),
    "ownership": AnalystNodeSpec(
        key="ownership",
        agent_node="Institutional Ownership Analyst",
        clear_node="Msg Clear Ownership",
        tool_node="tools_ownership",
        report_key="ownership_report",
    ),
    "ratings": AnalystNodeSpec(
        key="ratings",
        agent_node="Analyst Ratings Analyst",
        clear_node="Msg Clear Ratings",
        tool_node="tools_ratings",
        report_key="ratings_report",
    ),
    "short_interest": AnalystNodeSpec(
        key="short_interest",
        agent_node="Short Interest Analyst",
        clear_node="Msg Clear Short Interest",
        tool_node="tools_short_interest",
        report_key="short_interest_report",
    ),
    "valuation": AnalystNodeSpec(
        key="valuation",
        agent_node="Valuation Analyst",
        clear_node="Msg Clear Valuation",
        tool_node="tools_valuation",
        report_key="valuation_report",
    ),
    "catalyst": AnalystNodeSpec(
        key="catalyst",
        agent_node="Catalyst Calendar Analyst",
        clear_node="Msg Clear Catalyst",
        tool_node="tools_catalyst",
        report_key="catalyst_report",
    ),
    "review": AnalystNodeSpec(
        key="review",
        agent_node="Performance Review Analyst",
        clear_node="Msg Clear Review",
        tool_node="tools_review",
        report_key="review_report",
    ),
}


def build_analyst_execution_plan(
    selected_analysts: Iterable[str],
    concurrency_limit: int = 1,
) -> AnalystExecutionPlan:
    if concurrency_limit < 1:
        raise ValueError("analyst concurrency limit must be >= 1")
    specs: list[AnalystNodeSpec] = []
    for analyst_key in selected_analysts:
        spec = ANALYST_NODE_SPECS.get(analyst_key)
        if spec is None:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        specs.append(spec)
    if not specs:
        raise ValueError("at least one analyst must be selected")
    return AnalystExecutionPlan(specs=specs, concurrency_limit=concurrency_limit)
