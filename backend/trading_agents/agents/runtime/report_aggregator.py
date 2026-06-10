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
        "review_report": "Hindsight Performance Review Report",
    }


def build_resources(state, report_fields: dict[str, str], prefix: str = "") -> str:
    """Return labelled, newline-separated non-empty reports from ``state``.

    ``prefix`` is prepended to each label (e.g. ``"### "`` for the synthesis
    manager / auditor, which render the sections as markdown headings)."""
    resources = []
    for field, label in report_fields.items():
        content = state.get(field, "")
        if content and content.strip():
            resources.append(f"{prefix}{label}:\n{content.strip()}")
    return "\n\n".join(resources)
