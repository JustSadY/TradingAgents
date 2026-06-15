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
from backend.trading_agents.agents.data.ownership_tools import get_catalyst_calendar, get_institutional_holdings
from backend.trading_agents.agents.data.quant_tools import get_quant_data
from backend.trading_agents.agents.data.search_tools import search_web
from backend.trading_agents.agents.data.sec_tools import get_insider_transactions_deep, get_sec_filings
from backend.trading_agents.agents.data.technical_indicators_tools import get_indicators

# Re-exporting tool functions for analyst modules
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
    "get_insider_transactions",
    "get_insider_transactions_deep",
    "get_institutional_holdings",
    "get_sec_filings",
    "get_news",
    "get_options_data",
    "get_quant_data",
    "run_strategy_backtest",
    "get_language_instruction",
    "build_instrument_context",
    "create_msg_delete",
]


def get_language_instruction() -> str:
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
