from __future__ import annotations

from backend.core.config import is_live_trading_enabled
from backend.core.constants import PAGE_KEYS, SETTING_KEYS, WEBHOOK_EVENTS
from backend.trading_agents.agent_catalog import label_for
from backend.trading_agents.agent_catalog import list_analysts as _engine_analysts
from backend.trading_agents.llm_clients.capabilities import get_supported_output_languages
from backend.trading_agents.llm_clients.registry import llm_registry

_RISK_DEBATE = "Risk Debate"

def _node_specs() -> dict:
    try:
        from backend.trading_agents.agents.runtime.analyst_execution import ANALYST_NODE_SPECS

        return ANALYST_NODE_SPECS
    except Exception:
        return {}

async def available_analysts(db=None, user=None) -> list[dict]:
    """Single source: the engine analyst catalog.

    When the graph is importable we only surface analysts that actually
    have a wired node spec.
    """
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
            out.append(
                {
                    "key": info.key,
                    "label": info.label,
                    "description": info.description,
                    "default": info.default_on,
                }
            )
    return out

def _analyst_label(key: str) -> str:
    return label_for(key)

SECTION_LABELS: dict[str, str] = {
    "market_report": "Market Analysis",
    "sentiment_report": "Sentiment Analysis",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamental Analysis",
    "macro_report": "Macro Analysis",
    "options_report": "Options Analysis",
    "quant_report": "Quantitative Analysis",
    "earnings_report": "Earnings Analysis",
    "insider_report": "Insider Activity",
    "ownership_report": "Institutional Ownership",
    "ratings_report": "Analyst Ratings",
    "short_interest_report": "Short Interest",
    "valuation_report": "Valuation Comparison",
    "catalyst_report": "Upcoming Catalysts",
    "review_report": "Performance Review",
    "agent_qa_report": "Analyst Cross-Examination",
    "investment_plan": "Research Evidence Summary",
    "trader_investment_plan": "Legacy Trader Proposal (historical only)",
    "trader_plan": "Legacy Trader Proposal (historical only)",
    "final_trade_decision": "Final Decision (Portfolio Manager)",
    "final_decision": "Final Decision (Portfolio Manager)",
    "bull_history": "Bull Arguments",
    "bear_history": "Bear Arguments",
    "investment_debate_history": "Debate",
    "risk_debate_history": _RISK_DEBATE,
    "judge_decision": "Judge Decision",
}
SIGNALS: list[dict] = [
    {"value": "Buy", "label": "Buy", "tone": "positive"},
    {"value": "Overweight", "label": "Overweight", "tone": "positive"},
    {"value": "Hold", "label": "Hold", "tone": "neutral"},
    {"value": "Underweight", "label": "Underweight", "tone": "negative"},
    {"value": "Sell", "label": "Sell", "tone": "negative"},
]
ASSET_TYPES: list[dict] = [
    {"value": "stock", "label": "Stock"},
    {"value": "crypto", "label": "Crypto"},
]
LANGUAGES: list[dict] = [
    {"value": "English", "label": "English"},
    {"value": "Turkish", "label": "Türkçe"},
    {"value": "German", "label": "Deutsch"},
    {"value": "French", "label": "Français"},
    {"value": "Spanish", "label": "Español"},
    {"value": "Chinese", "label": "中文"},
    {"value": "Japanese", "label": "日本語"},
    {"value": "Arabic", "label": "العربية"},
]
DATA_VENDORS: list[dict] = [
    {"value": "yfinance", "label": "yFinance"},
    {"value": "alpha_vantage", "label": "Alpha Vantage"},
]
TRADING_MODES: list[dict] = [
    {"value": "simulation", "label": "Simulation (Paper Trading)"},
    {"value": "live", "label": "Live"},
]
BROKERS: list[dict] = [
    {"value": "simulation", "label": "Simulation"},
    {"value": "alpaca", "label": "Alpaca (Paper/Live)"},
]
PROVIDER_LABELS: dict[str, str] = llm_registry.get_provider_labels()

EFFORT_OPTIONS: dict[str, list[dict]] = llm_registry.get_effort_options()

LLM_CATALOG: dict[str, dict] = {
    p.key: {
        "label": p.label,
        "models": [
            {
                "value": value,
                "label": label,
                "supported_output_languages": get_supported_output_languages(value),
            }
            for label, value in p.models
        ],
    }
    for p in llm_registry.list_providers()
}

def trading_options_for_user(user=None) -> tuple[list[dict], list[dict]]:
    """Return only brokerage choices the requesting user may safely configure.

    Paper Alpaca remains an owner-only option.  The real-money mode is omitted
    until the server operator explicitly enables it; non-owner administrators
    never receive either Alpaca or Live choices from the metadata API.
    """
    simulation_modes = [TRADING_MODES[0].copy()]
    simulation_brokers = [BROKERS[0].copy()]
    if user is None or not getattr(user, "is_owner", False):
        return simulation_modes, simulation_brokers

    if is_live_trading_enabled():
        return [choice.copy() for choice in TRADING_MODES], [choice.copy() for choice in BROKERS]

    return simulation_modes, [
        simulation_brokers[0],
        {"value": "alpaca", "label": "Alpaca (Paper)"},
    ]

MEMORY_STORES: list[dict] = [
    {"value": "pinecone", "label": "Pinecone"},
    {"value": "pgvector", "label": "pgvector (PostgreSQL)"},
]

EMBEDDERS: list[dict] = [
    {"value": "pinecone", "label": "Pinecone hosted", "note": "No extra key needed"},
    {"value": "openai", "label": "OpenAI", "note": "Uses your OpenAI key"},
    {"value": "ollama", "label": "Ollama", "note": "Local, free"},
]

SECTIONS: list[dict] = [
    {"key": "market_report", "label": "Market Analysis", "category": "analyst", "order": 1, "icon": "BarChart"},
    {"key": "sentiment_report", "label": "Sentiment Analysis", "category": "analyst", "order": 2, "icon": "Activity"},
    {"key": "news_report", "label": "News Analysis", "category": "analyst", "order": 3, "icon": "Newspaper"},
    {"key": "fundamentals_report", "label": "Fundamental Analysis", "category": "analyst", "order": 4, "icon": "Scale"},
    {"key": "macro_report", "label": "Macro Analysis", "category": "analyst", "order": 5, "icon": "Globe"},
    {"key": "options_report", "label": "Options Analysis", "category": "analyst", "order": 6, "icon": "TrendingUp"},
    {"key": "quant_report", "label": "Quantitative Analysis", "category": "analyst", "order": 7, "icon": "Brain"},
    {"key": "earnings_report", "label": "Earnings Analysis", "category": "analyst", "order": 8, "icon": "DollarSign"},
    {"key": "insider_report", "label": "Insider Activity", "category": "analyst", "order": 9, "icon": "Eye"},
    {
        "key": "ownership_report",
        "label": "Institutional Ownership",
        "category": "analyst",
        "order": 10,
        "icon": "Users",
    },
    {"key": "ratings_report", "label": "Analyst Ratings", "category": "analyst", "order": 11, "icon": "Star"},
    {
        "key": "short_interest_report",
        "label": "Short Interest",
        "category": "analyst",
        "order": 12,
        "icon": "TrendingDown",
    },
    {"key": "valuation_report", "label": "Valuation Comparison", "category": "analyst", "order": 13, "icon": "Target"},
    {"key": "catalyst_report", "label": "Upcoming Catalysts", "category": "analyst", "order": 14, "icon": "Zap"},
    {"key": "review_report", "label": "Performance Review", "category": "research", "order": 15, "icon": "ShieldCheck"},
    {"key": "synthesis_report", "label": "Synthesis", "category": "research", "order": 16, "icon": "Brain"},
    {"key": "audit_report", "label": "Audit", "category": "research", "order": 17, "icon": "ShieldAlert"},
    {"key": "agent_qa_report", "label": "Cross-Examination", "category": "research", "order": 18, "icon": "Bot"},
    {"key": "investment_plan", "label": "Research Evidence Summary", "category": "research", "order": 19, "icon": "Target"},
    {"key": "trader_plan", "label": "Legacy Trader Proposal", "category": "trade", "order": 20, "icon": "History"},
    {"key": "bull_history", "label": "Bull Arguments", "category": "debate", "order": 21, "icon": "TrendingUp"},
    {"key": "bear_history", "label": "Bear Arguments", "category": "debate", "order": 22, "icon": "TrendingDown"},
    {
        "key": "investment_debate_history",
        "label": "Investment Debate",
        "category": "debate",
        "order": 23,
        "icon": "MessageSquare",
    },
    {"key": "risk_debate_history", "label": "Risk Debate", "category": "debate", "order": 24, "icon": "ShieldAlert"},
    {"key": "judge_decision", "label": "Judge Decision", "category": "decision", "order": 25, "icon": "Gavel"},
    {"key": "final_decision", "label": "Final Decision", "category": "decision", "order": 26, "icon": "CheckCircle"},
]

async def investor_personas(db=None, user=None) -> list[dict]:
    from backend.trading_agents.personas import list_personas

    builtins = [{"value": p.key, "label": p.label, "description": p.description} for p in list_personas()]
    if db is not None and user is not None:
        try:
            from backend.services import persona_service

            rows = await persona_service.get_user_personas(db, user.id)
            custom = [{"value": r.key, "label": r.label, "description": r.description} for r in rows]
            return builtins + custom
        except Exception:
            pass
    return builtins

ORDER_STATUSES: list[dict] = [
    {"value": "FILLED", "label": "Filled", "tone": "positive"},
    {"value": "PARTIALLY_FILLED", "label": "Partial", "tone": "neutral"},
    {"value": "PENDING", "label": "Pending", "tone": "neutral"},
    {"value": "REJECTED", "label": "Rejected", "tone": "negative"},
]
ORDER_ACTIONS: list[dict] = [
    {"value": "BUY", "label": "Buy", "tone": "positive"},
    {"value": "SELL", "label": "Sell", "tone": "negative"},
]
CHART_PERIODS: list[dict] = [
    {"value": "1m", "label": "1M"},
    {"value": "3m", "label": "3M"},
    {"value": "6m", "label": "6M"},
    {"value": "1y", "label": "1Y"},
    {"value": "2y", "label": "2Y"},
    {"value": "5y", "label": "5Y"},
]

async def build_meta(db=None, user=None) -> dict:
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.agent_catalog import list_agents
    from backend.trading_agents.agents.hierarchy import AgentHierarchy
    from backend.trading_agents.agents.tools import registry

    tools_list = registry.metadata()
    agents_list = [a.metadata() for a in list_agents()]
    if db is not None and user is not None:
        from backend.services.tool_access_service import get_user_tool_access

        agent_ctx = await build_agent_runtime_context(db, user.id)
        hierarchy = AgentHierarchy(agent_ctx)

        tool_access_map = await get_user_tool_access(db, user.id)

        filtered_tools = []
        for t in tools_list:
            if not user.is_admin and not tool_access_map.get(t["key"], {}).get("can_view", True):
                continue

            allowed = t.get("allowed_analysts", [])
            if allowed:
                is_any_agent_enabled = any(hierarchy.is_enabled(a) for a in allowed)
                if not is_any_agent_enabled:
                    continue

            filtered_tools.append(t)
        tools_list = filtered_tools
    trading_modes, brokers = trading_options_for_user(user)
    return {
        "analysts": await available_analysts(db, user),
        "tools": tools_list,
        "agents": agents_list,
        "section_labels": SECTION_LABELS,
        "signals": SIGNALS,
        "asset_types": ASSET_TYPES,
        "languages": LANGUAGES,
        "data_vendors": DATA_VENDORS,
        "trading_modes": trading_modes,
        "brokers": brokers,
        "provider_labels": PROVIDER_LABELS,
        "investor_personas": await investor_personas(db, user),
        "effort_options": EFFORT_OPTIONS,
        "order_statuses": ORDER_STATUSES,
        "order_actions": ORDER_ACTIONS,
        "chart_periods": CHART_PERIODS,
        "page_keys": PAGE_KEYS,
        "setting_keys": [{"value": key, "label": key} for key in SETTING_KEYS],
        "sections": SECTIONS,
        "webhook_events": WEBHOOK_EVENTS,
        "memory_stores": MEMORY_STORES,
        "embedders": EMBEDDERS,
    }

_STATIC_NODE_LABELS: dict[str, tuple[str, str]] = {
    "Market Intelligence": ("Market Intelligence", "analyst"),
    "Agent Q&A": ("Agent Q&A Cross-Examination", "analyst"),
    "Bull Researcher": ("Bull Researcher", "research"),
    "Bear Researcher": ("Bear Researcher", "research"),
    "Research Manager": ("Research Manager — investment plan", "research"),
    "Trader": ("Legacy Trader checkpoint", "trade"),
    _RISK_DEBATE: (_RISK_DEBATE, "risk"),
    "Aggressive Analyst": ("Aggressive Risk Analyst", "risk"),
    "Conservative Analyst": ("Conservative Risk Analyst", "risk"),
    "Neutral Analyst": ("Neutral Risk Analyst", "risk"),
    "Portfolio Manager": ("Portfolio Manager — final decision", "decision"),
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
