from __future__ import annotations
from typing import Any
from backend.trading_agents.agents.utils.rating import parse_rating
class SignalProcessor:
    def __init__(self, llm: Any = None):
        self.llm = llm
    def process_signal(self, full_signal: str) -> str:
        return parse_rating(full_signal)
