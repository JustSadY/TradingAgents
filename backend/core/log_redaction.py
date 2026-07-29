from __future__ import annotations

import logging
import os
import re
import traceback
from collections import OrderedDict
from threading import RLock

_logger = logging.getLogger(__name__)

_MASK = "***REDACTED***"
_SENSITIVE_ENV_VARS = (
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "ALPHA_VANTAGE_API_KEY",
)

# User-supplied strings such as webhook URLs can contain credentials in a
# path/query. Keep them redactable without letting a long-running server grow
# an unbounded permanent set as users rotate URLs or submit invalid values.
# OrderedDict acts as a small LRU and the lock protects logging threads as
# well as async request tasks.
_MAX_DYNAMIC_LITERALS = 1_000
_DYNAMIC_LITERALS: OrderedDict[str, None] = OrderedDict()
_DYNAMIC_LITERALS_LOCK = RLock()


def register_sensitive_literal(value: str):
    """Add a dynamic value to be masked in logs (e.g. user webhook URLs)."""
    if value and len(value) >= 6:
        with _DYNAMIC_LITERALS_LOCK:
            _DYNAMIC_LITERALS.pop(value, None)
            _DYNAMIC_LITERALS[value] = None
            while len(_DYNAMIC_LITERALS) > _MAX_DYNAMIC_LITERALS:
                _DYNAMIC_LITERALS.popitem(last=False)


def _dynamic_literals_snapshot() -> list[str]:
    """Return a stable longest-first literal list for one redaction pass."""
    with _DYNAMIC_LITERALS_LOCK:
        values = list(_DYNAMIC_LITERALS)
    return sorted(values, key=len, reverse=True)


_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]{12,}"),
    re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|secret|token|password)"
        r"(\"?\s*[:=]\s*\"?)([a-z0-9._\-]{6,})"
    ),
]


def _build_literals() -> list[str]:
    values: set[str] = set()
    for name in _SENSITIVE_ENV_VARS:
        val = os.environ.get(name)
        if val and len(val) >= 6:
            values.add(val)
    return sorted(values, key=len, reverse=True)


def redact_text(text: str, literals: list[str] | None = None) -> str:
    if not text:
        return text
    # Combine static environment-based literals with dynamic user-based
    # literals. Longest-first avoids partially masking a longer secret that
    # shares a prefix with another literal.
    combined_literals = (
        sorted(_dynamic_literals_snapshot() + _LITERALS, key=len, reverse=True) if literals is None else literals
    )
    for secret in combined_literals:
        if secret in text:
            text = text.replace(secret, _MASK)
    for pat in _PATTERNS:
        if pat.groups >= 3:
            text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASK}", text)
        else:
            text = pat.sub(_MASK, text)
    return text


_LITERALS = _build_literals()


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = redact_text(msg)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
            if record.exc_info:
                record.exc_text = redact_text("".join(traceback.format_exception(*record.exc_info)))
                record.exc_info = None
            elif record.exc_text:
                record.exc_text = redact_text(record.exc_text)
        except Exception:
            _logger.debug("Log redaction failed (non-fatal)")
        return True


redaction_filter = RedactionFilter()


def install_redaction(*handlers: logging.Handler) -> None:
    for h in handlers:
        if redaction_filter not in h.filters:
            h.addFilter(redaction_filter)
