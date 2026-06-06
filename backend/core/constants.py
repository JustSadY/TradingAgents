from typing import Set

# Application Structure
PAGE_KEYS = [
    "dashboard", "analysis", "chart", "watchlist", "orders", 
    "trading", "portfolio", "performance", "alerts", "ab-testing", 
    "logs", "profile", "settings"
]

SETTING_KEYS = ["general", "llm", "risk", "webhooks", "cron", "presets"]

# Analysis Signals
BUY_SIGNALS: Set[str] = {"Buy", "Overweight"}
SELL_SIGNALS: Set[str] = {"Sell", "Underweight"}
HOLD_SIGNALS: Set[str] = {"Hold"}

# Analysis Constants
DEFAULT_HOLDING_DAYS: int = 5
TOKENS_PER_ANALYST: int = 8000

# Indicative blended USD cost per 1K tokens, keyed by substring of the model id.
MODEL_COST_PER_1K: dict[str, float] = {
    "gpt-4o-mini": 0.00015,
    "gpt-4o": 0.005,
    "o1-mini": 0.003,
    "o1": 0.015,
    "o3-mini": 0.0011,
    "claude-3-5-sonnet": 0.003,
    "claude-3-5-haiku": 0.001,
    "claude-opus": 0.015,
    "claude-sonnet": 0.003,
    "gemini-1.5-pro": 0.007,
    "gemini-1.5-flash": 0.000075,
    "gemini-2.0-flash": 0.000075,
    "gemini-2.0": 0.000075,
}

# Tone mappings (could also be here if shared)
SIGNAL_TONES = {
    "Buy": "positive",
    "Overweight": "positive",
    "Hold": "neutral",
    "Underweight": "negative",
    "Sell": "negative",
}
