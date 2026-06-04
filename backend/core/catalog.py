from __future__ import annotations
from backend.trading_agents.analyst_catalog import list_analysts as _engine_analysts, label_for
def _node_specs() -> dict:
    try:
        from backend.trading_agents.graph.analyst_execution import ANALYST_NODE_SPECS
        return ANALYST_NODE_SPECS
    except Exception:
        return {}
async def available_analysts(db=None, user=None) -> list[dict]:
    # Single source: the engine analyst catalog. When the graph is importable we
    # only surface analysts that actually have a wired node spec.
    specs = _node_specs()
    out: list[dict] = []
    
    agent_access_map = {}
    if db is not None and user is not None and not user.is_admin:
        from backend.services.tool_access_service import get_user_agent_access
        agent_access_map = await get_user_agent_access(db, user.id)

    for info in _engine_analysts():
        if not specs or info.key in specs:
            if user is not None and not user.is_admin:
                if not agent_access_map.get(info.key, True):
                    continue
            out.append({
                "key": info.key,
                "label": info.label,
                "description": info.description,
                "default": info.default_on,
            })
    return out
def _analyst_label(key: str) -> str:
    return label_for(key)
SECTION_LABELS: dict[str, str] = {
    "market_report":             "Market Analysis",
    "sentiment_report":          "Sentiment Analysis",
    "news_report":               "News Analysis",
    "fundamentals_report":       "Fundamental Analysis",
    "macro_report":              "Macro Analysis",
    "options_report":            "Options Analysis",
    "quant_report":              "Quantitative Analysis",
    "earnings_report":           "Earnings Analysis",
    "review_report":             "Performance Review",
    "investment_plan":           "Investment Plan",
    "trader_investment_plan":    "Trader Plan",
    "trader_plan":               "Trader Plan",
    "final_trade_decision":      "PM Decision",
    "final_decision":            "PM Decision",
    "bull_history":              "Bull Arguments",
    "bear_history":              "Bear Arguments",
    "investment_debate_history": "Debate",
    "risk_debate_history":       "Risk Debate",
    "judge_decision":            "Judge Decision",
}
SIGNALS: list[dict] = [
    {"value": "Buy",         "label": "Al",    "tone": "positive"},
    {"value": "Overweight",  "label": "Artır", "tone": "positive"},
    {"value": "Hold",        "label": "Tut",   "tone": "neutral"},
    {"value": "Underweight", "label": "Azalt", "tone": "negative"},
    {"value": "Sell",        "label": "Sat",   "tone": "negative"},
]
ASSET_TYPES: list[dict] = [
    {"value": "stock",  "label": "Hisse"},
    {"value": "crypto", "label": "Kripto"},
]
LANGUAGES: list[dict] = [
    {"value": "English",  "label": "English"},
    {"value": "Turkish",  "label": "Türkçe"},
    {"value": "German",   "label": "Deutsch"},
    {"value": "French",   "label": "Français"},
    {"value": "Spanish",  "label": "Español"},
    {"value": "Chinese",  "label": "中文"},
    {"value": "Japanese", "label": "日本語"},
    {"value": "Arabic",   "label": "العربية"},
]
DATA_VENDORS: list[dict] = [
    {"value": "yfinance",      "label": "yFinance"},
    {"value": "alpha_vantage", "label": "Alpha Vantage"},
]
TRADING_MODES: list[dict] = [
    {"value": "simulation", "label": "Simülasyon (Paper Trading)"},
    {"value": "live",       "label": "Canlı (Live)"},
]
BROKERS: list[dict] = [
    {"value": "simulation", "label": "Simülasyon"},
]
PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "google": "Google (Gemini)",
    "xai": "xAI (Grok)",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Global)",
    "qwen-cn": "Qwen (China)",
    "glm": "GLM / Z.AI (Global)",
    "glm-cn": "GLM / BigModel (China)",
    "minimax": "MiniMax (Global)",
    "minimax-cn": "MiniMax (China)",
    "ollama": "Ollama (Local)",
    "nvidia": "NVIDIA NIM",
    "litellm": "LiteLLM Proxy",
    "azure": "Azure OpenAI",
}
# Investor personas are owned by the engine persona registry; derive them so the
# UI never hardcodes the option list. Falls back to a static copy if the engine
# package cannot be imported.
_PERSONAS_FALLBACK: list[dict] = [
    {"value": "conservative", "label": "Muhafazakâr",
     "description": "Sermaye koruma, temettü ve düşük volatiliteli blue-chip odaklı"},
    {"value": "risk_loving", "label": "Risk Sever",
     "description": "Yüksek getiri, momentum, büyüme ve kripto için yüksek volatilite kabulü"},
    {"value": "esg_focused", "label": "ESG Odaklı",
     "description": "Çevre, sosyal ve yönetişim metrikleri finansal getiriyle birlikte önceliklendirilir"},
]


def investor_personas() -> list[dict]:
    try:
        from backend.trading_agents.personas import list_personas
        personas = list_personas()
        if personas:
            return [
                {"value": p.key, "label": p.label, "description": p.description}
                for p in personas
            ]
    except Exception:
        pass
    return _PERSONAS_FALLBACK


# Provider-specific reasoning/thinking effort levels (UI option lists).
EFFORT_OPTIONS: dict[str, list[dict]] = {
    "openai": [
        {"value": "low", "label": "Düşük"},
        {"value": "medium", "label": "Orta"},
        {"value": "high", "label": "Yüksek"},
    ],
    "anthropic": [
        {"value": "low", "label": "Düşük"},
        {"value": "medium", "label": "Orta"},
        {"value": "high", "label": "Yüksek"},
    ],
    "google": [
        {"value": "minimal", "label": "Minimal"},
        {"value": "low", "label": "Düşük"},
        {"value": "medium", "label": "Orta"},
        {"value": "high", "label": "Yüksek"},
    ],
}
ORDER_STATUSES: list[dict] = [
    {"value": "FILLED",           "label": "Gerçekleşti", "tone": "positive"},
    {"value": "PARTIALLY_FILLED", "label": "Kısmi",       "tone": "neutral"},
    {"value": "PENDING",          "label": "Bekliyor",    "tone": "neutral"},
    {"value": "REJECTED",         "label": "Reddedildi",  "tone": "negative"},
]
ORDER_ACTIONS: list[dict] = [
    {"value": "BUY",  "label": "Al",  "tone": "positive"},
    {"value": "SELL", "label": "Sat", "tone": "negative"},
]
# Chart time ranges supported by /api/market/ohlcv (single source for the UI).
CHART_PERIODS: list[dict] = [
    {"value": "1m", "label": "1A"},
    {"value": "3m", "label": "3A"},
    {"value": "6m", "label": "6A"},
    {"value": "1y", "label": "1Y"},
    {"value": "2y", "label": "2Y"},
    {"value": "5y", "label": "5Y"},
]


async def build_meta(db=None, user=None) -> dict:
    from backend.trading_agents.agents.tools.registry import registry
    tools_list = registry.metadata()
    if db is not None and user is not None and not user.is_admin:
        from backend.services.tool_access_service import get_user_tool_access
        tool_access_map = await get_user_tool_access(db, user.id)
        tools_list = [
            t for t in tools_list
            if tool_access_map.get(t["key"], {}).get("can_view", True)
        ]
    return {
        "analysts": await available_analysts(db, user),
        "tools": tools_list,
        "section_labels": SECTION_LABELS,
        "signals": SIGNALS,
        "asset_types": ASSET_TYPES,
        "languages": LANGUAGES,
        "data_vendors": DATA_VENDORS,
        "trading_modes": TRADING_MODES,
        "brokers": BROKERS,
        "provider_labels": PROVIDER_LABELS,
        "investor_personas": investor_personas(),
        "effort_options": EFFORT_OPTIONS,
        "order_statuses": ORDER_STATUSES,
        "order_actions": ORDER_ACTIONS,
        "chart_periods": CHART_PERIODS,
    }
_STATIC_NODE_LABELS: dict[str, tuple[str, str]] = {
    "Bull Researcher":     ("Bull Researcher", "research"),
    "Bear Researcher":     ("Bear Researcher", "research"),
    "Research Manager":    ("Research Manager — investment plan", "research"),
    "Trader":              ("Trader — execution plan", "trade"),
    "Aggressive Analyst":  ("Aggressive Risk Analyst", "risk"),
    "Conservative Analyst": ("Conservative Risk Analyst", "risk"),
    "Neutral Analyst":     ("Neutral Risk Analyst", "risk"),
    "Portfolio Manager":   ("Portfolio Manager — final decision", "decision"),
}
_ANALYST_NODE_LABELS: dict[str, tuple[str, str]] | None = None
def _analyst_node_labels() -> dict[str, tuple[str, str]]:
    global _ANALYST_NODE_LABELS
    if _ANALYST_NODE_LABELS is None:
        mapping: dict[str, tuple[str, str]] = {}
        for key, spec in _node_specs().items():
            label = _analyst_label(key)
            mapping[spec.agent_node] = (f"{label} Analyst", "analyst")
            mapping[spec.tool_node] = (f"{label} — fetching data", "tool")
        _ANALYST_NODE_LABELS = mapping
    return _ANALYST_NODE_LABELS
def node_progress(node_name: str) -> dict | None:
    hit = _analyst_node_labels().get(node_name) or _STATIC_NODE_LABELS.get(node_name)
    if hit is None:
        return None
    label, stage = hit
    return {"type": "progress", "node": node_name, "label": label, "stage": stage}
