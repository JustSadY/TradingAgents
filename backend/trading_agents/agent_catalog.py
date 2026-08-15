from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentSettingField:
    key: str
    type: str
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
    category: str
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
            ],
        }

from backend.trading_agents.llm_clients.registry import llm_registry


def get_standard_agent_settings() -> list[AgentSettingField]:
    provider_options = [{"value": "", "label_key": "settings.analyst_default_provider"}]
    for p in llm_registry.list_providers():
        provider_options.append({"value": p.key, "label_key": p.label})

    return [
        AgentSettingField(
            key="llm_provider",
            type="select",
            label_key="LLM Provider",
            description_key="Select the LLM provider for this agent",
            default="",
            required=False,
            options=provider_options,
        ),
        AgentSettingField(
            key="llm_model",
            type="string",
            label_key="Model Name",
            description_key="Specify the model name (e.g. gpt-5.6-luna or claude-sonnet-5)",
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
        ),
    ]

AGENTS: list[AgentInfo] = [
    AgentInfo(
        "analysis_planner",
        "Analysis Planner",
        "Builds a direction-neutral investigation agenda from prior assumptions and open questions",
        "manager",
        True,
        get_standard_agent_settings(),
        "portfolio_manager",
    ),
    AgentInfo(
        "market_intelligence",
        "Market Intelligence",
        "Coordinates the data & indicator analyst sub-agents",
        "manager",
        True,
        get_standard_agent_settings(),
        "portfolio_manager",
    ),
    AgentInfo(
        "market",
        "Market Analyst",
        "Technical indicators, price trends and momentum",
        "analyst",
        True,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "social",
        "Social Analyst",
        "Social media, StockTwits and Reddit sentiment",
        "analyst",
        True,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "news",
        "News Analyst",
        "Company-specific and sector news flow",
        "analyst",
        True,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "fundamentals",
        "Fundamentals Analyst",
        "Balance sheet, income statement and valuation",
        "analyst",
        True,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "macro",
        "Macro Analyst",
        "Interest rates, inflation and economic outlook",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "options",
        "Options Analyst",
        "Options chain, implied volatility and flows",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "quant",
        "Quant Analyst",
        "Statistical factors and quantitative signals",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "earnings",
        "Earnings Analyst",
        "Earnings calls, estimates and surprises",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "insider",
        "Insider Activity Analyst",
        "Executive insider buys and sells (SEC Form 4)",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "ownership",
        "Institutional Ownership Analyst",
        "13F institutional and fund ownership changes",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "ratings",
        "Analyst Ratings Analyst",
        "Wall Street analyst recommendations and price targets",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "short_interest",
        "Short Interest Analyst",
        "Short interest, days-to-cover and squeeze positioning",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "valuation",
        "Valuation Analyst",
        "Relative valuation multiples vs sector benchmark",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "catalyst",
        "Catalyst Calendar Analyst",
        "Upcoming earnings, dividends and event risk windows",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "review",
        "Performance Review Analyst",
        "Performance review of past decisions",
        "analyst",
        False,
        get_standard_agent_settings(),
        "market_intelligence",
    ),
    AgentInfo(
        "bull_researcher",
        "Bull Researcher",
        "Advocates for long positions using positive indicators",
        "manager",
        True,
        get_standard_agent_settings(),
        "research_manager",
    ),
    AgentInfo(
        "bear_researcher",
        "Bear Researcher",
        "Advocates for short/hedged positions using risks",
        "manager",
        True,
        get_standard_agent_settings(),
        "research_manager",
    ),
    AgentInfo(
        "synthesis_manager",
        "Synthesis Manager",
        "Synthesizes analyst reports, alignments and conflicts",
        "manager",
        True,
        get_standard_agent_settings(),
        "research_manager",
    ),
    AgentInfo(
        "auditor",
        "Auditor",
        "Audits research quality, consistency, and completeness",
        "manager",
        True,
        get_standard_agent_settings(),
        "research_manager",
    ),
    AgentInfo(
        "research_manager",
        "Research Manager",
        "Formulates overall research summaries and investment plans",
        "manager",
        True,
        get_standard_agent_settings(),
        "portfolio_manager",
    ),
    AgentInfo(
        "risk_debate",
        "Risk Debate Manager",
        "Surfaces non-executable aggressive, neutral, and conservative risk guardrails",
        "manager",
        True,
        get_standard_agent_settings(),
        "portfolio_manager",
    ),
    AgentInfo(
        "strategy_reconciler",
        "Strategy Reconciler",
        "Compares structured fresh evidence with the active exact asset strategy",
        "manager",
        True,
        get_standard_agent_settings(),
        "portfolio_manager",
    ),
    AgentInfo(
        "decision_stability_controller",
        "Decision Stability Controller",
        "Deterministically validates material Portfolio Manager decision changes before execution",
        "manager",
        True,
        [],
        "portfolio_manager",
    ),
    AgentInfo(
        "portfolio_manager",
        "Portfolio Manager",
        "Produces the raw allocation proposal; the stability controller is the final execution authority",
        "manager",
        True,
        get_standard_agent_settings(),
        None,
    ),
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
