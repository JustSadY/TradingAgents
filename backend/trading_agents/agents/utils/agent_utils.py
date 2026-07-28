import asyncio

from langchain_core.messages import HumanMessage, RemoveMessage

from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.data.core_stock_tools import get_stock_data
from backend.trading_agents.agents.data.fundamental_data_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from backend.trading_agents.agents.data.macro_tools import get_macro_data
from backend.trading_agents.agents.data.news_data_tools import (
    get_global_news,
    get_insider_transactions,
    get_news,
)
from backend.trading_agents.agents.data.options_tools import get_options_data
from backend.trading_agents.agents.data.ownership_tools import (
    get_analyst_ratings,
    get_catalyst_calendar,
    get_institutional_holdings,
    get_short_interest,
    get_valuation_comparison,
)
from backend.trading_agents.agents.data.quant_tools import get_quant_data
from backend.trading_agents.agents.data.search_tools import search_web
from backend.trading_agents.agents.data.sec_tools import get_insider_transactions_deep, get_sec_filings
from backend.trading_agents.agents.data.technical_indicators_tools import get_indicators

__all__ = [
    "search_web",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_macro_data",
    "get_indicators",
    "get_stock_data",
    "get_global_news",
    "get_catalyst_calendar",
    "get_analyst_ratings",
    "get_short_interest",
    "get_valuation_comparison",
    "get_insider_transactions",
    "get_insider_transactions_deep",
    "get_institutional_holdings",
    "get_sec_filings",
    "get_news",
    "get_options_data",
    "get_quant_data",
    "run_strategy_backtest",
    "_get_language_instruction",
    "get_general_settings_block",
    "get_system_instruction_override",
    "build_instrument_context",
    "create_msg_delete",
    "run_macd_rsi_backtests",
]


def _get_language_instruction() -> str:
    from backend.trading_agents.dataflows.config import get_config

    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return (
        f"\n\n**CRITICAL LANGUAGE REQUIREMENT:** You MUST write your ENTIRE response in {lang}. "
        f"This is a strict, non-negotiable requirement. Do NOT use any other language under any circumstances. "
        f"Even if source data, tool outputs, or retrieved content are in a different language, "
        f"all of your analysis, commentary, headings, and narrative text MUST be written in {lang}."
    )


def get_system_instruction_override(agent_key: str) -> str | None:
    """Return *agent_key*'s Settings → Agents "System Prompt Override" text.

    Returns ``None`` when unset/blank, so callers can keep their own default
    instruction text. Reads the same ``active_run_context`` context-var the
    analyst node factory uses, so it works with zero wiring from the graph.
    """
    from backend.trading_agents.agents.data.chart_tools import active_run_context

    ctx = active_run_context.get(None)
    if not ctx or "graph" not in ctx:
        return None
    graph = ctx["graph"]
    runtime_agent_ctx = (getattr(graph, "config", {}) or {}).get("runtime_agent_context", {})
    agent_state = runtime_agent_ctx.get(agent_key, {}) if isinstance(runtime_agent_ctx, dict) else {}
    settings = agent_state.get("settings", {}) if isinstance(agent_state, dict) else {}
    override = settings.get("system_instruction") if isinstance(settings, dict) else None
    return override.strip() if isinstance(override, str) and override.strip() else None


def get_general_settings_block() -> str:
    """Return all general settings that should be appended to every agent system prompt.

    Add new global settings here — they will automatically apply to all agents
    that go through run_tool_analyst, and to any agent that calls this function.
    """
    parts = []
    lang = _get_language_instruction()
    if lang:
        parts.append(lang)
    return "".join(parts)


def build_instrument_context(ticker: str, asset_type: str = "stock") -> str:
    instrument_label = "asset" if asset_type == "crypto" else "instrument"
    extra_hint = (
        " Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available."
        if asset_type == "crypto"
        else ""
    )
    return (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)." + extra_hint
    )


def create_msg_delete():
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}

    return delete_messages


async def run_macd_rsi_backtests(ticker: str, trade_date: str | None = None) -> tuple[str, str]:
    macd_args = {"ticker": ticker, "strategy_type": "macd_crossover"}
    rsi_args = {"ticker": ticker, "strategy_type": "rsi_oversold"}
    if trade_date:
        macd_args["curr_date"] = trade_date
        rsi_args["curr_date"] = trade_date

    macd_results, rsi_results = await asyncio.gather(
        asyncio.to_thread(run_strategy_backtest.invoke, macd_args),
        asyncio.to_thread(run_strategy_backtest.invoke, rsi_args),
    )
    return macd_results, rsi_results
