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
_RATING_LABEL_RE = re.compile(
    r"^\s*(?:final\s+)?rating\s*[:\-]\s*\**\s*(buy|overweight|hold|underweight|sell)\b", re.IGNORECASE
)
_RATING_TOKEN_RE = re.compile(r"\b(buy|overweight|hold|underweight|sell)\b", re.IGNORECASE)


def parse_rating(text: str, default: str = "Hold") -> str:
    lines = text.splitlines()
    for line in lines:
        m = _RATING_LABEL_RE.search(line)
        if m:
            return m.group(1).capitalize()
    structured_candidates = []
    for line in lines:
        stripped = line.strip().lower()
        if not stripped:
            continue
        if stripped.startswith("final") or stripped.startswith("decision") or stripped.startswith("signal"):
            structured_candidates.extend(m.group(1).lower() for m in _RATING_TOKEN_RE.finditer(line))
    unique_structured = []
    for c in structured_candidates:
        if c in _RATING_SET and c not in unique_structured:
            unique_structured.append(c)
    if len(unique_structured) == 1:
        return unique_structured[0].capitalize()
    return default
