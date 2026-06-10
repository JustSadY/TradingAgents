"""Helper for assembling analyst report sections into a single prompt block.

The bull/bear researchers and the three risk debators each repeated the same
loop: iterate a ``{state_field: label}`` mapping, keep non-empty reports, and
join them. The label wording differs between agents (it is part of each agent's
prompt), so callers keep their own mapping and only share the loop.
"""

from __future__ import annotations


def build_report_fields(news_label: str, fundamentals_label: str) -> dict[str, str]:
    """The standard ``{state_field: label}`` mapping shared by the bull/bear
    researchers and the three risk debators. Only the news and fundamentals
    labels vary between them, so they're passed in."""
    return {
        "market_report": "Market Research Report",
        "sentiment_report": "Social Media Sentiment Report",
        "news_report": news_label,
        "fundamentals_report": fundamentals_label,
        "macro_report": "Macroeconomic Indicators Report",
        "options_report": "Options Market Derivatives Report",
        "quant_report": "Quantitative Metrics Report",
        "earnings_report": "Corporate Guidance & Earnings Report",
        "insider_report": "Insider Activity Report",
        "ownership_report": "Institutional Ownership Report",
        "catalyst_report": "Upcoming Catalysts Report",
        "review_report": "Hindsight Performance Review Report",
    }


def tail_history(history: str, limit: int | None = None) -> str:
    """Keep only the most recent ``limit`` chars of an accumulating debate
    transcript. Each researcher/debator re-sends the whole growing history on
    every turn, so without this the prompt size grows with each round. Reads
    ``max_debate_history_chars`` from config when ``limit`` is omitted."""
    history = (history or "").strip()
    if limit is None:
        try:
            from backend.trading_agents.dataflows.config import get_config

            limit = int(get_config().get("max_debate_history_chars", 8000))
        except Exception:  # noqa: BLE001
            limit = 0
    if limit <= 0 or len(history) <= limit:
        return history
    return "…[earlier debate turns omitted]\n" + history[-limit:]


def _truncate_report(content: str, limit: int) -> str:
    """Trim a single report to ``limit`` chars, keeping the head (where analysts
    put the executive summary) and flagging the cut so the LLM knows it's partial."""
    content = content.strip()
    if limit <= 0 or len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n…[report truncated to conserve tokens]"


def build_resources(state, report_fields: dict[str, str], prefix: str = "", max_chars_per_report: int | None = None) -> str:
    """Return labelled, newline-separated non-empty reports from ``state``.

    ``prefix`` is prepended to each label (e.g. ``"### "`` for the synthesis
    manager / auditor, which render the sections as markdown headings).

    ``max_chars_per_report`` caps each report's size before it is re-sent to a
    downstream agent. The bull/bear researchers and the three risk debators each
    receive the *full* set of analyst reports on every turn, so an uncapped
    11-analyst run re-sends tens of thousands of tokens per debate round. When
    omitted, the cap is read from the run config (``max_report_chars_in_prompts``)."""
    if max_chars_per_report is None:
        try:
            from backend.trading_agents.dataflows.config import get_config

            max_chars_per_report = int(get_config().get("max_report_chars_in_prompts", 6000))
        except Exception:  # noqa: BLE001 — config is best-effort; fall back to no cap
            max_chars_per_report = 0

    resources = []
    for field, label in report_fields.items():
        content = state.get(field, "")
        if content and content.strip():
            resources.append(f"{prefix}{label}:\n{_truncate_report(content, max_chars_per_report)}")
    return "\n\n".join(resources)
