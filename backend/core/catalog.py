from __future__ import annotations
from backend.trading_agents.agent_catalog import list_analysts as _engine_analysts, label_for
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
    {"value": "Buy",         "label": "Buy",         "tone": "positive"},
    {"value": "Overweight",  "label": "Overweight",  "tone": "positive"},
    {"value": "Hold",        "label": "Hold",        "tone": "neutral"},
    {"value": "Underweight", "label": "Underweight", "tone": "negative"},
    {"value": "Sell",        "label": "Sell",        "tone": "negative"},
]
ASSET_TYPES: list[dict] = [
    {"value": "stock",  "label": "Stock"},
    {"value": "crypto", "label": "Crypto"},
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
    {"value": "simulation", "label": "Simulation (Paper Trading)"},
    {"value": "live",       "label": "Live"},
]
BROKERS: list[dict] = [
    {"value": "simulation", "label": "Simulation"},
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
}
def investor_personas() -> list[dict]:
    from backend.trading_agents.personas import list_personas
    return [
        {"value": p.key, "label": p.label, "description": p.description}
        for p in list_personas()
    ]


# Provider-specific reasoning/thinking effort levels (UI option lists).
EFFORT_OPTIONS: dict[str, list[dict]] = {
    "openai": [
        {"value": "low", "label": "Low"},
        {"value": "medium", "label": "Medium"},
        {"value": "high", "label": "High"},
    ],
    "anthropic": [
        {"value": "low", "label": "Low"},
        {"value": "medium", "label": "Medium"},
        {"value": "high", "label": "High"},
    ],
    "google": [
        {"value": "minimal", "label": "Minimal"},
        {"value": "low", "label": "Low"},
        {"value": "medium", "label": "Medium"},
        {"value": "high", "label": "High"},
    ],
}
ORDER_STATUSES: list[dict] = [
    {"value": "FILLED",           "label": "Filled",      "tone": "positive"},
    {"value": "PARTIALLY_FILLED", "label": "Partial",     "tone": "neutral"},
    {"value": "PENDING",          "label": "Pending",     "tone": "neutral"},
    {"value": "REJECTED",         "label": "Rejected",    "tone": "negative"},
]
ORDER_ACTIONS: list[dict] = [
    {"value": "BUY",  "label": "Buy",  "tone": "positive"},
    {"value": "SELL", "label": "Sell", "tone": "negative"},
]
# Chart time ranges supported by /api/market/ohlcv (single source for the UI).
CHART_PERIODS: list[dict] = [
    {"value": "1m", "label": "1M"},
    {"value": "3m", "label": "3M"},
    {"value": "6m", "label": "6M"},
    {"value": "1y", "label": "1Y"},
    {"value": "2y", "label": "2Y"},
    {"value": "5y", "label": "5Y"},
]


async def build_meta(db=None, user=None) -> dict:
    from backend.trading_agents.agents.tools.registry import registry
    from backend.trading_agents.agent_catalog import list_agents
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.agents.hierarchy import AgentHierarchy

    tools_list = registry.metadata()
    agents_list = [a.metadata() for a in list_agents()]
    if db is not None and user is not None:
        from backend.services.tool_access_service import get_user_tool_access
        
        # 1. Build hierarchy knowledge
        agent_ctx = await build_agent_runtime_context(db, user.id)
        hierarchy = AgentHierarchy(agent_ctx)
        
        tool_access_map = await get_user_tool_access(db, user.id)
        
        filtered_tools = []
        for t in tools_list:
            # Check permission block for non-admin
            if not user.is_admin and not tool_access_map.get(t["key"], {}).get("can_view", True):
                continue
            
            # Check if any associated agent is active in the hierarchy
            allowed = t.get("allowed_analysts", [])
            if allowed:
                is_any_agent_enabled = any(hierarchy.is_enabled(a) for a in allowed)
                if not is_any_agent_enabled:
                    continue
                
            filtered_tools.append(t)
        tools_list = filtered_tools
    return {
        "analysts": await available_analysts(db, user),
        "tools": tools_list,
        "agents": agents_list,
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
