"""Helper for assembling analyst report sections into a single prompt block.

The bull/bear researchers and the three risk debators each repeated the same
loop: iterate a ``{state_field: label}`` mapping, keep non-empty reports, and
join them. The label wording differs between agents (it is part of each agent's
prompt), so callers keep their own mapping and only share the loop.
"""

from __future__ import annotations

import re

_SUMMARY_HEADING = re.compile(
    r"#{0,4}\s*(?:\d+[.)]\s*)?\**\s*executive\s+summary\b[:*\s]*",
    re.IGNORECASE,
)
_NEXT_HEADING = re.compile(
    r"\n\s{0,3}(?:#{1,4}\s|\**\s*\d+[.)]\s|\*\*[A-Z])",
)


def extract_executive_summary(report: str, max_chars: int = 1200) -> str | None:
    """Return just the Executive Summary section of an analyst report, or None
    when the report has no recognisable summary heading.

    Lets downstream agents reason over each analyst's conclusion (a few hundred
    tokens) instead of the full report with all its data tables (thousands)."""
    if not report:
        return None
    m = _SUMMARY_HEADING.search(report)
    if not m:
        return None
    start = m.end()
    nxt = _NEXT_HEADING.search(report, start)
    summary = (report[start : nxt.start()] if nxt else report[start:]).strip()
    if not summary:
        return None
    return summary[:max_chars].rstrip() + ("…" if len(summary) > max_chars else "")


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
        "ratings_report": "Analyst Ratings Report",
        "short_interest_report": "Short Interest Report",
        "valuation_report": "Valuation Comparison Report",
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
        except Exception:
            limit = 0
    if limit <= 0 or len(history) <= limit:
        return history
    truncated = history[-limit:]
    first_newline = truncated.find("\n")
    if first_newline != -1:
        truncated = truncated[first_newline + 1 :]
    return "…[earlier debate turns omitted]\n" + truncated


def middle_truncate(text: str, limit: int) -> str:
    """Trim oversized text while keeping both the head and the tail.

    Tool outputs are often chronological CSVs: the header/context sits at the
    top and the most recent (most relevant) rows at the bottom, so plain head
    truncation would discard exactly the data the analyst needs. Keeps ~25% of
    the budget from the head and ~75% from the tail."""
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    head = max(1, limit // 4)
    tail = max(1, limit - head)

    head_text = text[:head]
    last_nl_head = head_text.rfind("\n")
    if last_nl_head != -1:
        head_text = head_text[:last_nl_head]

    tail_text = text[-tail:]
    first_nl_tail = tail_text.find("\n")
    if first_nl_tail != -1:
        tail_text = tail_text[first_nl_tail + 1 :]

    return head_text.rstrip() + "\n\n…[middle truncated to conserve tokens]…\n\n" + tail_text.lstrip()


def _truncate_report(content: str, limit: int) -> str:
    """Trim a single report to ``limit`` chars, keeping the head (where analysts
    put the executive summary) and flagging the cut so the LLM knows it's partial."""
    content = content.strip()
    if limit <= 0 or len(content) <= limit:
        return content
    truncated = content[:limit]
    last_nl = truncated.rfind("\n")
    if last_nl != -1:
        truncated = truncated[:last_nl]
    return truncated.rstrip() + "\n…[report truncated to conserve tokens]"


def build_resources(
    state,
    report_fields: dict[str, str],
    prefix: str = "",
    max_chars_per_report: int | None = None,
    summary_only: bool = False,
) -> str:
    """Return labelled, newline-separated non-empty reports from ``state``.

    ``prefix`` is prepended to each label (e.g. ``"### "`` for the synthesis
    manager / auditor, which render the sections as markdown headings).

    ``max_chars_per_report`` caps each report's size before it is re-sent to a
    downstream agent. The bull/bear researchers and the three risk debators each
    receive the *full* set of analyst reports on every turn, so an uncapped
    11-analyst run re-sends tens of thousands of tokens per debate round. When
    omitted, the cap is read from the run config (``max_report_chars_in_prompts``).

    ``summary_only`` sends just each report's Executive Summary when one exists
    (falling back to the truncated full report otherwise). Use it for agents that
    debate the analysts' *conclusions* rather than re-deriving from raw tables —
    the synthesis manager already produced the conflict map they actually need."""
    if max_chars_per_report is None:
        try:
            from backend.trading_agents.dataflows.config import get_config

            max_chars_per_report = int(get_config().get("max_report_chars_in_prompts", 6000))
        except Exception:
            max_chars_per_report = 0

    resources = []
    for field, label in report_fields.items():
        content = state.get(field, "")
        if not (content and content.strip()):
            continue
        if summary_only:
            summary = extract_executive_summary(content)
            rendered = summary if summary is not None else _truncate_report(content, max_chars_per_report)
        else:
            rendered = _truncate_report(content, max_chars_per_report)
        resources.append(f"{prefix}{label}:\n{rendered}")
    return "\n\n".join(resources)
