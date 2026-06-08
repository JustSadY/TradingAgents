from __future__ import annotations

import asyncio
import functools

from langchain_core.messages import AIMessage

from backend.trading_agents.agents.data.backtest_tools import run_strategy_backtest
from backend.trading_agents.agents.runtime.structured import (
    bind_structured,
)
from backend.trading_agents.agents.schemas import TraderProposal, render_trader_proposal
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    async def trader_node(state, name):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        investment_plan = state["investment_plan"]

        # Auto-pull the user's real account state (cash + holdings) so sizing is
        # grounded in actual figures instead of manually-entered ones.
        from backend.trading_agents.agents.runtime.portfolio_context import get_portfolio_context
        from backend.trading_agents.dataflows.config import get_config

        portfolio_context = await get_portfolio_context(get_config().get("user_id"))
        portfolio_block = f"{portfolio_context}\n\n" if portfolio_context else ""

        macd_args = {"ticker": company_name, "strategy_type": "macd_crossover"}
        rsi_args = {"ticker": company_name, "strategy_type": "rsi_oversold"}
        if state.get("trade_date"):
            macd_args["curr_date"] = state["trade_date"]
            rsi_args["curr_date"] = state["trade_date"]

        # run_strategy_backtest is synchronous and CPU/IO-heavy; keep it off the
        # event loop so it doesn't stall concurrent analyses.
        macd_results = await asyncio.to_thread(run_strategy_backtest.invoke, macd_args)
        rsi_results = await asyncio.to_thread(run_strategy_backtest.invoke, rsi_args)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior execution trader. Your task is to turn an investment plan into a precise trade proposal. "
                    "You must provide an 'Action' (Buy/Hold/Sell), 'Entry Price', 'Stop Loss', and 'Take Profit'. "
                    "CRITICAL: You must estimate a 'Confidence Score' (Win Probability) from 0.0 to 1.0 based on the "
                    "strength of the research plan and technical backtests. "
                    "You must also calculate the 'Kelly Criterion Size' (0.0 to 1.0) using the formula: K% = W - (1-W)/R, "
                    "where W is Confidence Score and R is Risk/Reward Ratio ((Take Profit - Entry) / (Entry - Stop Loss)). "
                    "When the user's current portfolio (cash available + holdings) is provided, multiply the Kelly Size by the cash available to provide the 'Suggested Capital Allocation', and never size a position larger than the available cash. "
                    "If Action is 'Hold' or 'Sell' (to close), set Kelly Size and Suggested Capital to 0. "
                    "If the user already holds this ticker (see their portfolio), account for the existing position when proposing an action. "
                    "Consider the 'GLOBAL MARKET PULSE' for overall market conditions. "
                    "Anchor your reasoning in the analysts' reports and the quantitative backtest results provided."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{portfolio_block}"
                    f"Research Plan: {investment_plan}\n\n"
                    f"Historical Strategy Backtests:\n{macd_results}\n\n{rsi_results}\n\n"
                    f"{instrument_context}\n\n"
                    "Formulate a precise trade proposal with confidence metrics, Kelly positioning, and risk warnings."
                ),
            },
        ]

        from backend.trading_agents.agents.runtime.structured import ainvoke_structured_or_freetext

        trader_proposal = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            "Trader",
        )

        # The helper returns a free-text string on fallback, or the structured
        # TraderProposal object when structured output succeeds.
        if isinstance(trader_proposal, str):
            trader_plan = trader_proposal
            proposal_json = "{}"
        else:
            trader_plan = render_trader_proposal(trader_proposal)
            proposal_json = trader_proposal.model_dump_json()

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "trader_proposal_json": proposal_json,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
