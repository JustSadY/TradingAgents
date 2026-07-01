from __future__ import annotations

import re

RATINGS_5_TIER: tuple[str, ...] = (
    "Buy",
    "Overweight",
    "Hold",
    "Underweight",
    "Sell",
)
_RATING_SET = {r.lower() for r in RATINGS_5_TIER}
# Leading markdown / emphasis noise a model may put before a label:
# "**Rating**", "## Final Decision", "- Signal", "> Recommendation", etc.
_LEADING_MD = r"[\s#>*_\-]*"
_DECISION_KEYWORDS = r"(?:rating|recommendation|decision|signal|action)"
# Tolerate emphasis both BEFORE the keyword and around the ``:``/``-`` separator,
# so ``**Rating**: Buy`` (the exact output of render_pm_decision) is matched.
_RATING_LABEL_RE = re.compile(
    rf"^{_LEADING_MD}(?:final\s+)?{_DECISION_KEYWORDS}\s*\**\s*[:\-]\s*\**\s*(buy|overweight|hold|underweight|sell)\b",
    re.IGNORECASE,
)
_RATING_TOKEN_RE = re.compile(r"\b(buy|overweight|hold|underweight|sell)\b", re.IGNORECASE)
_DECISION_PREFIXES = ("final", "decision", "signal", "rating", "recommendation", "action")


def parse_rating(text: str, default: str | None = "Hold") -> str | None:
    """Extract a Buy/Overweight/Hold/Underweight/Sell rating, or ``default``."""
    return parse_rating_matched(text, default)[0]


def parse_rating_matched(text: str, default: str | None = "Hold") -> tuple[str | None, bool]:
    """Like :func:`parse_rating` but also report whether a rating was actually found.

    Returns ``(rating, matched)``; ``matched`` is ``False`` when the result is the
    fallback default because no rating could be located — useful for telemetry.
    """
    lines = text.splitlines()
    for line in lines:
        m = _RATING_LABEL_RE.search(line)
        if m:
            return m.group(1).capitalize(), True
    structured_candidates = []
    for line in lines:
        # Strip leading markdown so headings like "## Final Decision: ..." are seen.
        stripped = line.strip().lstrip("#>*_- ").strip().lower()
        if not stripped:
            continue
        if stripped.startswith(_DECISION_PREFIXES):
            structured_candidates.extend(m.group(1).lower() for m in _RATING_TOKEN_RE.finditer(line))
    unique_structured = []
    for c in structured_candidates:
        if c in _RATING_SET and c not in unique_structured:
            unique_structured.append(c)
    if len(unique_structured) == 1:
        return unique_structured[0].capitalize(), True
    return default, False
