from langchain_core.prompts import ChatPromptTemplate

from backend.trading_agents.agents.runtime.report_aggregator import middle_truncate
from backend.trading_agents.agents.utils.agent_utils import get_general_settings_block

# Per-section cap: with many tickers the combined plans/decisions dominate the
# prompt, and the allocation needs each ticker's conclusion, not every detail.
_MAX_SECTION_CHARS = 4000


def create_super_portfolio_manager(llm):
    def super_portfolio_manager_node(state: dict):
        ticker_reports = state.get("ticker_reports", {})
        portfolio_context = state.get("portfolio_context", "")
        context_str = ""
        for ticker, report in ticker_reports.items():
            context_str += f"\n--- Ticker: {ticker} ---\n"
            context_str += (
                f"Trader Plan: {middle_truncate(report.get('trader_plan') or 'No plan', _MAX_SECTION_CHARS)}\n"
            )
            context_str += (
                "Portfolio Manager Decision: "
                f"{middle_truncate(report.get('portfolio_decision') or 'No decision', _MAX_SECTION_CHARS)}\n"
            )
        from backend.trading_agents.default_config import DEFAULT_CONFIG

        system_message = (
            DEFAULT_CONFIG.get(
                "super_portfolio_manager_prompt",
                "You are a Super Portfolio Manager for a hedge fund. Allocate the portfolio across these assets based on their reports.",
            )
            + get_general_settings_block()
        )
        portfolio_block = f"{portfolio_context}\n\n" if portfolio_context else ""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                (
                    "user",
                    f"{portfolio_block}Here are the final decisions from the trading team for the selected assets:"
                    f"\n\n{context_str}\n\nAllocate the user's actual cash available across these assets "
                    "(use the real figures above; keep an explicit cash position when appropriate). "
                    "Provide the final portfolio allocation and strategy.",
                ),
            ]
        )
        chain = prompt | llm
        result = chain.invoke({})
        return {"super_portfolio_report": result.content}

    return super_portfolio_manager_node
