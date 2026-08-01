from datetime import timedelta

PAGE_KEYS = [
    "dashboard",
    "analysis",
    "chart",
    "watchlist",
    "orders",
    "trading",
    "portfolio",
    "performance",
    "backtest",
    "alerts",
    "ab-testing",
    "logs",
    "profile",
    "settings",
    "screener",
    "sector-rotation",
    "earnings",
]

SETTING_KEYS = [
    "general",
    "llm",
    "agents",
    "tools",
    "risk",
    "alerts",
    "webhooks",
    "cron",
    "presets",
    "memory",
    "personas",
]

WEBHOOK_EVENTS: tuple[str, ...] = (
    "analysis_complete",
    "trade_executed",
    "alert_triggered",
    "signal_flip",
)

PERIOD_DELTAS = {
    "1m": timedelta(days=31),
    "3m": timedelta(days=92),
    "6m": timedelta(days=183),
    "1y": timedelta(days=365),
    "2y": timedelta(days=730),
    "5y": timedelta(days=1825),
}

BUY_SIGNALS: set[str] = {"Buy", "Overweight"}
SELL_SIGNALS: set[str] = {"Sell", "Underweight"}
HOLD_SIGNALS: set[str] = {"Hold"}

DEFAULT_HOLDING_DAYS: int = 5
TOKENS_PER_ANALYST: int = 8000

SIGNAL_SENTIMENT_VALUES = {
    "Buy": 0.85,
    "Overweight": 0.45,
    "Hold": 0.0,
    "Neutral": 0.0,
    "Underweight": -0.45,
    "Sell": -0.85,
}

SIGNAL_TONES = {
    "Buy": "positive",
    "Overweight": "positive",
    "Hold": "neutral",
    "Underweight": "negative",
    "Sell": "negative",
}

SIGNAL_TO_ACTION: dict[str, str] = {
    "Buy": "BUY",
    "Overweight": "BUY",
    "Sell": "SELL",
    "Underweight": "SELL",
}

BULLISH_SIGNALS: set[str] = {"buy", "overweight"}
BEARISH_SIGNALS: set[str] = {"sell", "underweight"}

def signal_direction(signal: str | None) -> str:
    s = (signal or "").strip().lower()
    if s in BULLISH_SIGNALS:
        return "bullish"
    if s in BEARISH_SIGNALS:
        return "bearish"
    return "neutral"
