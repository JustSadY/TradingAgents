from __future__ import annotations

import logging
from typing import Any

from backend.trading_agents.agents.runtime.rating import parse_rating_matched

_logger = logging.getLogger(__name__)


class SignalProcessor:
    def __init__(self, llm: Any = None):
        self.llm = llm

    def process_signal(self, full_signal: str) -> str:
        rating, matched = parse_rating_matched(full_signal)
        if not matched:
            # No rating could be located — the run silently defaults. Surface it
            # so a broken decision format (see the render/parse mismatch that made
            # every run return Hold) is visible instead of masked.
            _logger.warning(
                "Signal parse found no rating in decision text; defaulting to %r.",
                rating,
            )
            try:
                from backend.core.metrics import SIGNAL_PARSE_FALLBACK

                SIGNAL_PARSE_FALLBACK.inc()
            except Exception:  # noqa: BLE001 — metrics are best-effort / optional
                pass
        return rating
