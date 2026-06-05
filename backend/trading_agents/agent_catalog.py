from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentSettingField:
    key: str
    type: str  # "boolean", "number", "string", "textarea", "select"
    label_key: str
    description_key: str | None = None
    placeholder_key: str | None = None
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class AgentInfo:
    key: str
    label: str
    description: str
    category: str  # "analyst" or "manager"
    default_enabled: bool
    settings_schema: list[AgentSettingField] = field(default_factory=list)
    parent_key: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "default_enabled": self.default_enabled,
            "parent_key": self.parent_key,
            "settings_schema": [
                {
                    "key": field.key,
                    "type": field.type,
                    "label_key": field.label_key,
                    "description_key": field.description_key,
                    "placeholder_key": field.placeholder_key,
                    "default": field.default,
                    "required": field.required,
                    "min": field.min,
                    "max": field.max,
                    "step": field.step,
                    "options": field.options,
                }
                for field in self.settings_schema
            ]
        }


def get_standard_agent_settings() -> list[AgentSettingField]:
    return [
        AgentSettingField(
            key="llm_provider",
            type="select",
            label_key="LLM Provider",
            description_key="Select the LLM provider for this agent",
            default="",
            required=False,
            options=[
                {"value": "", "label_key": "settings.analyst_default_provider"},
                {"value": "openai", "label_key": "OpenAI"},
                {"value": "anthropic", "label_key": "Anthropic (Claude)"},
                {"value": "google", "label_key": "Google (Gemini)"},
                {"value": "xai", "label_key": "xAI (Grok)"},
                {"value": "deepseek", "label_key": "DeepSeek"},
                {"value": "qwen", "label_key": "Qwen (Global)"},
                {"value": "glm", "label_key": "GLM / Z.AI (Global)"},
                {"value": "minimax", "label_key": "MiniMax (Global)"},
                {"value": "ollama", "label_key": "Ollama (Local)"},
                {"value": "nvidia", "label_key": "NVIDIA NIM"},
                {"value": "litellm", "label_key": "LiteLLM Proxy"},
                {"value": "azure", "label_key": "Azure OpenAI"},
            ]
        ),
        AgentSettingField(
            key="llm_model",
            type="string",
            label_key="Model Name",
            description_key="Specify the model name (e.g. gpt-4o-mini or claude-3-5-sonnet)",
            placeholder_key="settings.analyst_default_model",
            default="",
            required=False,
        ),
        AgentSettingField(
            key="temperature",
            type="number",
            label_key="Temperature",
            description_key="LLM sampling temperature",
            default=0.0,
            required=True,
            min=0.0,
            max=2.0,
            step=0.1,
        ),
        AgentSettingField(
            key="system_instruction",
            type="textarea",
            label_key="System Prompt Override",
            description_key="Override the default system instructions (leave empty for default)",
            default="",
            required=False,
        )
    ]


AGENTS: list[AgentInfo] = [
    # ── Tier-1 Main Agent: Market Intelligence (owns the analyst sub-agents) ──
    AgentInfo("market_intelligence", "Market Intelligence", "Coordinates the data & indicator analyst sub-agents", "manager", True, get_standard_agent_settings(), "portfolio_manager"),

    # Analysts — Tier-2 sub-agents under Market Intelligence
    AgentInfo("market", "Market Analyst", "Technical indicators, price trends and momentum", "analyst", True, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("social", "Social Analyst", "Social media, StockTwits and Reddit sentiment", "analyst", True, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("news", "News Analyst", "Company-specific and sector news flow", "analyst", True, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("fundamentals", "Fundamentals Analyst", "Balance sheet, income statement and valuation", "analyst", True, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("macro", "Macro Analyst", "Interest rates, inflation and economic outlook", "analyst", False, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("options", "Options Analyst", "Options chain, implied volatility and flows", "analyst", False, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("quant", "Quant Analyst", "Statistical factors and quantitative signals", "analyst", False, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("earnings", "Earnings Analyst", "Earnings calls, estimates and surprises", "analyst", False, get_standard_agent_settings(), "market_intelligence"),
    AgentInfo("review", "Performance Review Analyst", "Performance review of past decisions", "analyst", False, get_standard_agent_settings(), "market_intelligence"),

    # ── Research branch: sub-agents under Research Manager ──
    AgentInfo("bull_researcher", "Bull Researcher", "Advocates for long positions using positive indicators", "manager", True, get_standard_agent_settings(), "research_manager"),
    AgentInfo("bear_researcher", "Bear Researcher", "Advocates for short/hedged positions using risks", "manager", True, get_standard_agent_settings(), "research_manager"),
    AgentInfo("synthesis_manager", "Synthesis Manager", "Synthesizes analyst reports, alignments and conflicts", "manager", True, get_standard_agent_settings(), "research_manager"),
    AgentInfo("auditor", "Auditor", "Audits research quality, consistency, and completeness", "manager", True, get_standard_agent_settings(), "research_manager"),

    # ── Tier-1 Main Agents under the Portfolio Manager root ──
    AgentInfo("research_manager", "Research Manager", "Formulates overall research summaries and investment plans", "manager", True, get_standard_agent_settings(), "portfolio_manager"),
    AgentInfo("trader", "Trader Agent", "Creates tactical execution strategy and sizing plans", "manager", True, get_standard_agent_settings(), "portfolio_manager"),
    AgentInfo("risk_debate", "Risk Debate Manager", "Orchestrates aggressive, neutral, and conservative risk debate", "manager", True, get_standard_agent_settings(), "portfolio_manager"),
    AgentInfo("portfolio_manager", "Portfolio Manager", "Makes final asset allocation and trade decisions", "manager", True, get_standard_agent_settings(), None),
]


def list_agents() -> list[AgentInfo]:
    return AGENTS


def get_agent(key: str) -> AgentInfo | None:
    for a in AGENTS:
        if a.key == key:
            return a
    return None


@dataclass(frozen=True)
class AnalystInfo:
    key: str
    label: str
    description: str
    default_on: bool


ANALYSTS: list[AnalystInfo] = [
    AnalystInfo(
        key=_a.key,
        label=_a.label,
        description=_a.description,
        default_on=_a.default_enabled,
    )
    for _a in AGENTS
    if _a.category == "analyst"
]

_ANALYSTS_BY_KEY = {a.key: a for a in ANALYSTS}


def list_analysts() -> list[AnalystInfo]:
    return list(ANALYSTS)


def get_analyst(key: str) -> AnalystInfo | None:
    return _ANALYSTS_BY_KEY.get(key)


def label_for(key: str) -> str:
    info = _ANALYSTS_BY_KEY.get(key)
    return info.label if info else key.title()
