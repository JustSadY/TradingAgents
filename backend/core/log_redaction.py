from __future__ import annotations

import logging
import os
import re
import traceback

_MASK = "***REDACTED***"
_SENSITIVE_ENV_VARS = (
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "ALPHA_VANTAGE_API_KEY",
)

_DYNAMIC_LITERALS: set[str] = set()


def register_sensitive_literal(value: str):
    """Add a dynamic value to be masked in logs (e.g. user webhook URLs)."""
    if value and len(value) >= 6:
        _DYNAMIC_LITERALS.add(value)


_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(
        r"(?i)(api[_-]?key|api[_-]?secret|secret|token|password)"
        r"(\"?\s*[:=]\s*\"?)([A-Za-z0-9._\-]{6,})"
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
    # Combine static environment-based literals with dynamic user-based literals
    combined_literals = (list(_DYNAMIC_LITERALS) + _LITERALS) if literals is None else literals
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
            pass
        return True


redaction_filter = RedactionFilter()


def install_redaction(*handlers: logging.Handler) -> None:
    for h in handlers:
        if redaction_filter not in h.filters:
            h.addFilter(redaction_filter)
