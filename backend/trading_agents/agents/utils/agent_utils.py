from langchain_core.messages import HumanMessage, RemoveMessage

# Re-exporting tool functions for analyst modules
from backend.trading_agents.agents.utils.core_stock_tools import get_stock_data
from backend.trading_agents.agents.utils.technical_indicators_tools import get_indicators
from backend.trading_agents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from backend.trading_agents.agents.utils.sec_tools import (
    get_sec_filings,
    get_insider_transactions_deep,
)
from backend.trading_agents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news,
)
from backend.trading_agents.agents.utils.macro_tools import get_macro_data
from backend.trading_agents.agents.utils.options_tools import get_options_data
from backend.trading_agents.agents.utils.search_tools import (
    search_web,
    get_crypto_fear_and_greed_index,
)
from backend.trading_agents.agents.utils.quant_tools import get_quant_data
from backend.trading_agents.agents.utils.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.utils.review_tools import get_past_performance_data


def get_language_instruction() -> str:
    from backend.trading_agents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


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
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`, `-USD`)."
        + extra_hint
    )


def create_msg_delete():
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}
    return delete_messages
