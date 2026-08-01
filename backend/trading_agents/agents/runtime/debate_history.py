"""Canonical formatting for investment and risk debate transcripts.

The graph keeps debate history as a single string because it is re-sent to
downstream agents as prompt context.  That representation is deliberately
simple, but it is *not* safe to render by splitting on every newline: a single
analyst response often contains paragraphs, lists, or Markdown headings.  This
module converts that internal transcript into stable ``sender``/``content``
records at the API/WebSocket boundary while remaining compatible with the
historical string format already stored in the database.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

_SENDER_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^bull(?:\s+(?:researcher|analyst))?$", re.IGNORECASE), "Bull Analyst"),
    (re.compile(r"^bear(?:\s+(?:researcher|analyst))?$", re.IGNORECASE), "Bear Analyst"),
    (
        re.compile(r"^aggressive(?:\s+(?:risk\s+)?(?:analyst|debator))?$", re.IGNORECASE),
        "Aggressive Analyst",
    ),
    (
        re.compile(r"^conservative(?:\s+(?:risk\s+)?(?:analyst|debator))?$", re.IGNORECASE),
        "Conservative Analyst",
    ),
    (
        re.compile(r"^neutral(?:\s+(?:risk\s+)?(?:analyst|debator))?$", re.IGNORECASE),
        "Neutral Analyst",
    ),
    (re.compile(r"^(?:portfolio\s+)?manager$", re.IGNORECASE), "Portfolio Manager"),
    (re.compile(r"^system$", re.IGNORECASE), "System"),
)

_SPEAKER_NAMES = (
    r"bull(?:\s+(?:researcher|analyst))?"
    r"|bear(?:\s+(?:researcher|analyst))?"
    r"|aggressive(?:\s+(?:risk\s+)?(?:analyst|debator))?"
    r"|conservative(?:\s+(?:risk\s+)?(?:analyst|debator))?"
    r"|neutral(?:\s+(?:risk\s+)?(?:analyst|debator))?"
    r"|(?:portfolio\s+)?manager"
    r"|system"
)
_SPEAKER_HEADER = re.compile(
    rf"^[ \t]*(?:#{{1,6}}[ \t]+)?(?:\d+[.)][ \t]+)?(?:[-*][ \t]+)?"
    rf"(?:\*{{1,3}}[ \t]*)?(?P<label>{_SPEAKER_NAMES})(?:[ \t]*\*{{1,3}})?"
    rf"[ \t]*(?::|[—–-][ \t]+|$)",
    re.IGNORECASE | re.MULTILINE,
)

def canonical_debate_sender(value: object, *, default: str = "System") -> str:
    """Map provider/legacy speaker labels to the stable UI contract."""
    label = str(value or "").strip().strip("*# \t:")
    for pattern, canonical in _SENDER_ALIASES:
        if pattern.fullmatch(label):
            return canonical
    return label or default

def text_from_response(response: object) -> str:
    """Extract readable text from the common LangChain provider response shapes."""
    content = getattr(response, "content", response)
    return _text_from_content(content)

def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        for key in ("text", "content"):
            if key in content:
                return _text_from_content(content[key])
        return ""
    if isinstance(content, Iterable) and not isinstance(content, (bytes, bytearray)):
        parts = [_text_from_content(item) for item in content]
        return "\n".join(part for part in parts if part).strip()
    return "" if content is None else str(content).strip()

def clean_debate_content(value: object, sender: str | None = None) -> str:
    """Remove a duplicated leading speaker heading without stripping Markdown body text."""
    text = _text_from_content(value).replace("\r\n", "\n").strip()
    if not text:
        return ""

    first = _SPEAKER_HEADER.match(text)
    if first:
        heading_sender = canonical_debate_sender(first.group("label"))
        if sender is None or heading_sender == canonical_debate_sender(sender):
            text = text[first.end() :].lstrip(" \t:\n—–-").strip()

    text = re.sub(r"^(?:\*{1,3}|_{1,3})[ \t]*(?:\n+|$)", "", text).strip()
    return text

def format_debate_argument(sender: str, response: object, *, empty_notice: str | None = None) -> str:
    """Create one canonical internal transcript entry for a model response."""
    canonical_sender = canonical_debate_sender(sender, default=sender)
    content = clean_debate_content(text_from_response(response), canonical_sender)
    if not content and empty_notice:
        content = empty_notice
    return f"{canonical_sender}: {content}" if content else ""

def debate_messages(value: object) -> list[dict[str, str]]:
    """Convert a legacy string or structured payload into display-safe messages.

    Old history rows remain readable, and new rows are stored as this list of
    records.  Each record holds the entire multiline response of one speaker.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        sender = value.get("sender")
        content = value.get("content")
        if isinstance(sender, str) and content is not None:
            cleaned = clean_debate_content(content, sender)
            return [{"sender": canonical_debate_sender(sender), "content": cleaned}] if cleaned else []
        return []
    if isinstance(value, (list, tuple)):
        messages: list[dict[str, str]] = []
        for item in value:
            messages.extend(debate_messages(item))
        return messages
    if not isinstance(value, str):
        return []

    text = value.replace("\r\n", "\n").strip()
    if not text:
        return []
    if text.startswith(("[", "{")):
        try:
            return debate_messages(json.loads(text))
        except (TypeError, ValueError):
            pass

    headers = list(_SPEAKER_HEADER.finditer(text))
    if not headers:
        return [{"sender": "System", "content": text}]

    messages: list[dict[str, str]] = []
    prefix = text[: headers[0].start()].strip()
    if prefix:
        messages.append({"sender": "System", "content": prefix})
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        sender = canonical_debate_sender(header.group("label"))
        content = clean_debate_content(text[header.end() : end], sender)
        if content:
            messages.append({"sender": sender, "content": content})
    return messages
